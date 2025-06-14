"""Text ingestion for Paul Graham essays - no chunking, each essay as single vector."""

import hashlib
import json
import time
from pathlib import Path
from typing import List, Dict, Optional
import structlog
from openai import OpenAI
import tiktoken

from app.deps import get_config, get_openai_client, get_vector_db
from app.monitoring import CostTracker
from app.exceptions import OpenAIError, VectorDBError

logger = structlog.get_logger(__name__)


class PaulGrahamProcessor:
    """Process Paul Graham essays from text files."""
    
    def __init__(self):
        self.source_dir = Path("data/source_material/paulGrahamEssays")
        
    def process_all_essays(self) -> List[Dict[str, any]]:
        """Process all Paul Graham essays from text files."""
        if not self.source_dir.exists():
            logger.warning("Paul Graham essays directory not found", path=str(self.source_dir))
            return []
        
        essays = []
        txt_files = list(self.source_dir.glob("*.txt"))
        
        if not txt_files:
            logger.warning("No .txt files found in Paul Graham essays directory")
            return []
        
        logger.info("Processing Paul Graham essays", file_count=len(txt_files))
        
        for txt_file in txt_files:
            try:
                # Read essay text
                with open(txt_file, 'r', encoding='utf-8') as f:
                    text = f.read().strip()
                
                if not text:
                    logger.warning("Empty file skipped", file=str(txt_file))
                    continue
                
                # Create essay record
                essay = {
                    "title": txt_file.stem,  # filename without extension
                    "text": text,
                    "word_count": len(text.split()),
                    "file_path": str(txt_file),
                    "essay_hash": self._get_text_hash(text)
                }
                
                essays.append(essay)
                logger.debug("Processed essay", 
                           title=essay["title"], 
                           word_count=essay["word_count"])
                
            except Exception as e:
                logger.error("Failed to process essay", file=str(txt_file), error=str(e))
                continue
        
        logger.info("Essay processing complete", 
                   total_essays=len(essays),
                   total_words=sum(essay["word_count"] for essay in essays))
        
        return essays
    
    def _get_text_hash(self, text: str) -> str:
        """Generate hash for essay deduplication."""
        return hashlib.md5(text.encode()).hexdigest()


class PaulGrahamEmbeddingGenerator:
    """Generate embeddings for full Paul Graham essays."""
    
    def __init__(self, model: str = "text-embedding-3-small"):
        self.client = get_openai_client()
        self.model = model
        self.cost_tracker = CostTracker()
        self.tokenizer = tiktoken.encoding_for_model("text-embedding-3-small")
        self.max_tokens = 8192  # Model context limit
    
    def generate_embeddings(self, essays: List[Dict[str, any]], 
                          batch_size: int = 1) -> List[Dict[str, any]]:
        """Generate embeddings for full essays in batches."""
        total_essays = len(essays)
        logger.info("Starting embedding generation for Paul Graham essays", 
                   total_essays=total_essays, 
                   model=self.model,
                   batch_size=batch_size)
        
        embedded_essays = []
        
        for i in range(0, total_essays, batch_size):
            batch = essays[i:i + batch_size]
            batch_texts = []
            
            # Process each essay in batch and truncate if needed
            for essay in batch:
                text = essay["text"]
                tokens = self.tokenizer.encode(text)
                
                if len(tokens) > self.max_tokens:
                    # Truncate to fit context window
                    truncated_tokens = tokens[:self.max_tokens]
                    text = self.tokenizer.decode(truncated_tokens)
                    logger.warning("Essay truncated due to token limit", 
                                 title=essay["title"],
                                 original_tokens=len(tokens),
                                 truncated_tokens=len(truncated_tokens))
                
                batch_texts.append(text)
            
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
                        "api_time_ms": int(api_time * 1000),
                        "account": "paulgraham"
                    }
                )
                
                # Add embeddings to essays
                for j, embedding_data in enumerate(response.data):
                    essay_idx = i + j
                    embedded_essay = essays[essay_idx].copy()
                    embedded_essay["embedding"] = embedding_data.embedding
                    embedded_essays.append(embedded_essay)
                
                logger.debug("Batch embedding complete", 
                           batch_start=i,
                           tokens_used=total_tokens,
                           cost_usd=batch_cost,
                           api_time_ms=int(api_time * 1000))
                
                # Rate limiting: small delay between batches
                if i + batch_size < total_essays:
                    time.sleep(0.2)
                
            except Exception as e:
                logger.error("Embedding batch failed", 
                           batch_start=i, 
                           error=str(e))
                raise OpenAIError(f"Essay embedding generation failed: {str(e)}")
        
        logger.info("Paul Graham embedding generation complete", 
                   total_essays=len(embedded_essays))
        
        return embedded_essays


class PaulGrahamVectorDB:
    """Manage ChromaDB operations for Paul Graham essays."""
    
    def __init__(self, collection_name: str = "paulgraham_knowledge"):
        self.client = get_vector_db()
        self.collection_name = collection_name
        self.collection = None
    
    def get_or_create_collection(self):
        """Get existing Paul Graham collection or create new one."""
        try:
            # Try to get existing collection
            self.collection = self.client.get_collection(name=self.collection_name)
            logger.info("Using existing Paul Graham collection", name=self.collection_name)
        except:
            # Create new collection
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "Paul Graham essays knowledge base - full essays as single vectors"}
            )
            logger.info("Created new Paul Graham collection", name=self.collection_name)
        
        return self.collection
    
    def store_essays(self, essays: List[Dict[str, any]]) -> int:
        """Store full essays in vector database."""
        if not self.collection:
            self.get_or_create_collection()
        
        logger.info("Storing Paul Graham essays in vector database", count=len(essays))
        
        # Prepare data for ChromaDB
        ids = []
        embeddings = []
        documents = []
        metadatas = []
        
        for essay in essays:
            # Create unique ID based on essay title and hash
            essay_id = f"pg_{essay['title']}_{essay['essay_hash'][:8]}"
            
            ids.append(essay_id)
            embeddings.append(essay["embedding"])
            documents.append(essay["text"])
            metadatas.append({
                "title": essay["title"],
                "word_count": essay["word_count"],
                "essay_hash": essay["essay_hash"],
                "file_path": essay["file_path"],
                "type": "full_essay",
                "author": "paul_graham"
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
            logger.info("Successfully stored Paul Graham essays", count=stored_count)
            return stored_count
            
        except Exception as e:
            logger.error("Failed to store Paul Graham essays", error=str(e))
            raise VectorDBError(f"Failed to store essays: {str(e)}")
    
    def get_collection_stats(self) -> Dict[str, any]:
        """Get statistics about the Paul Graham collection."""
        if not self.collection:
            self.get_or_create_collection()
        
        try:
            count = self.collection.count()
            
            # Get all metadata to analyze essays
            if count > 0:
                results = self.collection.get()
                
                titles = []
                total_words = 0
                
                for metadata in results["metadatas"]:
                    titles.append(metadata["title"])
                    total_words += metadata["word_count"]
                
                return {
                    "total_essays": count,
                    "essay_titles": titles,
                    "total_words": total_words,
                    "avg_words_per_essay": total_words // count if count > 0 else 0
                }
            else:
                return {
                    "total_essays": 0,
                    "essay_titles": [],
                    "total_words": 0,
                    "avg_words_per_essay": 0
                }
                
        except Exception as e:
            logger.error("Failed to get Paul Graham collection stats", error=str(e))
            raise VectorDBError(f"Failed to get collection stats: {str(e)}")


def process_paulgraham_essays():
    """Complete pipeline: Text files -> embeddings -> vector DB (no chunking)."""
    logger.info("Starting Paul Graham essay ingestion pipeline")
    
    # Step 1: Process text files
    processor = PaulGrahamProcessor()
    essays = processor.process_all_essays()
    
    if not essays:
        logger.warning("No Paul Graham essays to process")
        return
    
    # Step 2: Generate embeddings (no chunking - full essays)
    embedding_generator = PaulGrahamEmbeddingGenerator()
    embedded_essays = embedding_generator.generate_embeddings(essays)
    
    # Step 3: Store in dedicated vector database collection
    vector_manager = PaulGrahamVectorDB()
    stored_count = vector_manager.store_essays(embedded_essays)
    
    # Step 4: Show final stats
    stats = vector_manager.get_collection_stats()
    
    logger.info("Paul Graham ingestion pipeline complete",
               essays_processed=len(essays),
               essays_stored=stored_count,
               **stats)
    
    print(f"\n✅ Paul Graham Essays Ingestion Complete!")
    print(f"📚 Essays processed: {len(essays)}")
    print(f"💾 Essays stored: {stored_count}")
    print(f"📄 Total words: {stats['total_words']:,}")
    print(f"📊 Avg words/essay: {stats['avg_words_per_essay']:,}")
    print(f"🎯 Collection name: paulgraham_knowledge")
    print(f"\n📝 Essays included:")
    for title in sorted(stats['essay_titles']):
        print(f"   • {title}")
    
    return stats


def main():
    """Main function to run Paul Graham essay ingestion."""
    try:
        stats = process_paulgraham_essays()
        
        if stats and stats["total_essays"] > 0:
            print(f"\n🚀 Paul Graham agent ready! Knowledge base contains {stats['total_essays']} essays with {stats['total_words']:,} total words.")
        else:
            print("\n❌ No Paul Graham essays were ingested. Please check the data/source_material/paulGrahamEssays/ directory.")
    
    except Exception as e:
        logger.error("Paul Graham ingestion pipeline failed", error=str(e))
        print(f"\n❌ Paul Graham ingestion failed: {str(e)}")
        raise


if __name__ == "__main__":
    main()