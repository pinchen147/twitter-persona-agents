"""
Text chunking and embedding pipeline - Knowledge base construction system.

This module implements the complete data ingestion pipeline that transforms PDF books
into searchable vector embeddings. It's the foundation of the bot's knowledge base,
enabling semantic search and context-aware tweet generation.

Pipeline Stages:
1. PDF Processing: Extract clean text from philosophical books
2. Text Chunking: Split into large, context-rich segments (1500 words)
3. Embedding Generation: Create vector representations via OpenAI
4. Vector Storage: Persist in ChromaDB for retrieval

Key Features:
- Large chunk sizes preserve philosophical context
- Overlapping chunks ensure concept continuity
- Hash-based deduplication prevents redundancy
- Batch processing for efficiency
- Cost tracking for OpenAI API calls

Architecture:
- TextChunker: Creates overlapping text segments
- EmbeddingGenerator: Manages OpenAI embedding API
- VectorDBManager: Handles ChromaDB operations

The ingestion process runs offline and populates the knowledge base
that powers the bot's philosophical tweet generation. Each chunk
maintains enough context for meaningful content synthesis.
"""

import hashlib
import json
import time
from pathlib import Path
from typing import List, Dict, Optional
import structlog
from openai import OpenAI

from app.deps import get_config, get_openai_client, get_vector_db
from app.monitoring import CostTracker
from app.exceptions import OpenAIError, VectorDBError
from ingest.ingest_pdf import PDFProcessor

logger = structlog.get_logger(__name__)


class TextChunker:
    """Split text into large, context-rich chunks."""
    
    def __init__(self, chunk_size: int = 1500, chunk_overlap: int = 200):
        self.chunk_size = chunk_size  # words
        self.chunk_overlap = chunk_overlap  # words
    
    def chunk_text(self, text: str, source_title: str) -> List[Dict[str, any]]:
        """Split text into overlapping chunks."""
        words = text.split()
        total_words = len(words)
        
        if total_words <= self.chunk_size:
            # If text is small enough, return as single chunk
            return [{
                "text": text,
                "chunk_index": 0,
                "source_title": source_title,
                "word_count": total_words,
                "chunk_hash": self._get_text_hash(text)
            }]
        
        chunks = []
        chunk_index = 0
        start_idx = 0
        
        while start_idx < total_words:
            # Calculate end index
            end_idx = min(start_idx + self.chunk_size, total_words)
            
            # Extract chunk words
            chunk_words = words[start_idx:end_idx]
            chunk_text = ' '.join(chunk_words)
            
            # Create chunk record
            chunk = {
                "text": chunk_text,
                "chunk_index": chunk_index,
                "source_title": source_title,
                "word_count": len(chunk_words),
                "start_word_idx": start_idx,
                "end_word_idx": end_idx,
                "chunk_hash": self._get_text_hash(chunk_text)
            }
            
            chunks.append(chunk)
            
            # Move to next chunk with overlap
            start_idx += self.chunk_size - self.chunk_overlap
            chunk_index += 1
            
            # Break if we've processed all text
            if end_idx >= total_words:
                break
        
        logger.info("Text chunking complete", 
                   source=source_title,
                   total_words=total_words,
                   chunks_created=len(chunks),
                   avg_chunk_size=total_words // len(chunks))
        
        return chunks
    
    def _get_text_hash(self, text: str) -> str:
        """Generate hash for chunk deduplication."""
        return hashlib.md5(text.encode()).hexdigest()


class EmbeddingGenerator:
    """Generate embeddings using OpenAI API."""
    
    def __init__(self, model: str = "text-embedding-3-small"):
        self.client = get_openai_client()
        self.model = model
        self.cost_tracker = CostTracker()
    
    def generate_embeddings(self, chunks: List[Dict[str, any]], 
                          batch_size: int = 100) -> List[Dict[str, any]]:
        """Generate embeddings for text chunks in batches."""
        total_chunks = len(chunks)
        logger.info("Starting embedding generation", 
                   total_chunks=total_chunks, 
                   model=self.model,
                   batch_size=batch_size)
        
        embedded_chunks = []
        
        for i in range(0, total_chunks, batch_size):
            batch = chunks[i:i + batch_size]
            batch_texts = [chunk["text"] for chunk in batch]
            
            try:
                logger.debug("Processing embedding batch", 
                           batch_start=i, 
                           batch_size=len(batch))
                
                # Call OpenAI API
                start_time = time.time()
                response = self.client.embeddings.create(
                    input=batch_texts,
                    model=self.model
                )
                api_time = time.time() - start_time
                
                # Calculate cost (approximate)
                total_tokens = response.usage.total_tokens
                cost_per_token = 0.00002 / 1000  # $0.02 per 1M tokens for text-embedding-3-small
                batch_cost = total_tokens * cost_per_token
                
                # Record cost
                self.cost_tracker.record_cost(
                    service="openai",
                    operation="embedding",
                    cost_usd=batch_cost,
                    tokens_used=total_tokens,
                    metadata={
                        "model": self.model,
                        "batch_size": len(batch),
                        "api_time_ms": int(api_time * 1000)
                    }
                )
                
                # Add embeddings to chunks
                for j, embedding_data in enumerate(response.data):
                    chunk_idx = i + j
                    embedded_chunk = chunks[chunk_idx].copy()
                    embedded_chunk["embedding"] = embedding_data.embedding
                    embedded_chunks.append(embedded_chunk)
                
                logger.debug("Batch embedding complete", 
                           batch_start=i,
                           tokens_used=total_tokens,
                           cost_usd=batch_cost,
                           api_time_ms=int(api_time * 1000))
                
                # Rate limiting: small delay between batches
                if i + batch_size < total_chunks:
                    time.sleep(0.1)
                
            except Exception as e:
                logger.error("Embedding batch failed", 
                           batch_start=i, 
                           error=str(e))
                raise OpenAIError(f"Embedding generation failed: {str(e)}")
        
        logger.info("Embedding generation complete", 
                   total_chunks=len(embedded_chunks))
        
        return embedded_chunks


class VectorDBManager:
    """Manage ChromaDB operations."""
    
    def __init__(self):
        self.client = get_vector_db()
        config = get_config()
        self.collection_name = config.get("vector_db", {}).get("collection_name", "zen_kink_knowledge")
        self.collection = None
    
    def get_or_create_collection(self):
        """Get existing collection or create new one."""
        try:
            # Try to get existing collection
            self.collection = self.client.get_collection(name=self.collection_name)
            logger.info("Using existing collection", name=self.collection_name)
        except:
            # Create new collection
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "Zen Kink Bot knowledge base"}
            )
            logger.info("Created new collection", name=self.collection_name)
        
        return self.collection
    
    def store_chunks(self, chunks: List[Dict[str, any]]) -> int:
        """Store chunks in vector database."""
        if not self.collection:
            self.get_or_create_collection()
        
        logger.info("Storing chunks in vector database", count=len(chunks))
        
        # Prepare data for ChromaDB
        ids = []
        embeddings = []
        documents = []
        metadatas = []
        
        for i, chunk in enumerate(chunks):
            # Create unique ID
            chunk_id = f"{chunk['source_title']}_{chunk['chunk_index']}_{chunk['chunk_hash'][:8]}"
            
            ids.append(chunk_id)
            embeddings.append(chunk["embedding"])
            documents.append(chunk["text"])
            metadatas.append({
                "source_title": chunk["source_title"],
                "chunk_index": chunk["chunk_index"],
                "word_count": chunk["word_count"],
                "chunk_hash": chunk["chunk_hash"],
                "start_word_idx": chunk.get("start_word_idx", 0),
                "end_word_idx": chunk.get("end_word_idx", chunk["word_count"])
            })
        
        try:
            # Store in ChromaDB
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
            
            stored_count = len(ids)
            logger.info("Successfully stored chunks", count=stored_count)
            return stored_count
            
        except Exception as e:
            logger.error("Failed to store chunks", error=str(e))
            raise VectorDBError(f"Failed to store chunks: {str(e)}")
    
    def get_collection_stats(self) -> Dict[str, any]:
        """Get statistics about the collection."""
        if not self.collection:
            self.get_or_create_collection()
        
        try:
            count = self.collection.count()
            
            # Get sample of metadata to analyze sources
            if count > 0:
                sample_size = min(100, count)
                results = self.collection.get(limit=sample_size)
                
                sources = set()
                total_words = 0
                
                for metadata in results["metadatas"]:
                    sources.add(metadata["source_title"])
                    total_words += metadata["word_count"]
                
                return {
                    "total_chunks": count,
                    "unique_sources": len(sources),
                    "sources": list(sources),
                    "avg_words_per_chunk": total_words // len(results["metadatas"]) if results["metadatas"] else 0
                }
            else:
                return {
                    "total_chunks": 0,
                    "unique_sources": 0,
                    "sources": [],
                    "avg_words_per_chunk": 0
                }
                
        except Exception as e:
            logger.error("Failed to get collection stats", error=str(e))
            raise VectorDBError(f"Failed to get collection stats: {str(e)}")


def process_books_to_vectors():
    """Complete pipeline: PDF -> chunks -> embeddings -> vector DB."""
    logger.info("Starting complete ingestion pipeline")
    
    # Step 1: Process PDFs
    pdf_processor = PDFProcessor()
    books = pdf_processor.process_all_pdfs()
    
    if not books:
        logger.warning("No books to process")
        return
    
    # Step 2: Chunk text
    config = get_config()
    chunk_size = config.get("text_processing", {}).get("chunk_size", 1500)
    chunk_overlap = config.get("text_processing", {}).get("chunk_overlap", 200)
    
    chunker = TextChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    
    all_chunks = []
    for book in books:
        book_chunks = chunker.chunk_text(book["text"], book["title"])
        all_chunks.extend(book_chunks)
    
    logger.info("Text chunking complete", total_chunks=len(all_chunks))
    
    # Step 3: Generate embeddings
    config = get_config()
    embedding_model = config.get("openai", {}).get("embedding_model", "text-embedding-3-small")
    
    embedding_generator = EmbeddingGenerator(model=embedding_model)
    embedded_chunks = embedding_generator.generate_embeddings(all_chunks)
    
    # Step 4: Store in vector database
    vector_manager = VectorDBManager()
    stored_count = vector_manager.store_chunks(embedded_chunks)
    
    # Step 5: Show final stats
    stats = vector_manager.get_collection_stats()
    
    logger.info("Ingestion pipeline complete",
               books_processed=len(books),
               chunks_created=len(all_chunks),
               chunks_stored=stored_count,
               **stats)
    
    print(f"\n✅ Ingestion Complete!")
    print(f"📚 Books processed: {len(books)}")
    print(f"📄 Chunks created: {len(all_chunks)}")
    print(f"💾 Chunks stored: {stored_count}")
    print(f"🎯 Unique sources: {stats['unique_sources']}")
    print(f"📊 Avg words/chunk: {stats['avg_words_per_chunk']}")
    
    return stats


def main():
    """Main function to run the complete ingestion pipeline."""
    try:
        stats = process_books_to_vectors()
        
        if stats and stats["total_chunks"] > 0:
            print(f"\n🚀 Ready to generate tweets! Knowledge base contains {stats['total_chunks']} chunks from {stats['unique_sources']} sources.")
        else:
            print("\n❌ No content was ingested. Please add PDF files to data/source_material/ and try again.")
    
    except Exception as e:
        logger.error("Ingestion pipeline failed", error=str(e))
        print(f"\n❌ Ingestion failed: {str(e)}")
        raise


if __name__ == "__main__":
    main()