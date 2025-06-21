"""
Text ingestion for startup quotes and wisdom - processes text files into embeddings.

This module handles the ingestion of startup wisdom from various text files,
including Paul Graham essays, YC advice, and quotes from tech leaders.
"""

import hashlib
import re
from pathlib import Path
from typing import List, Dict
import structlog

from ingest.split_embed import TextChunker, EmbeddingGenerator, VectorDBManager
from app.exceptions import ConfigurationError

logger = structlog.get_logger(__name__)


class StartupQuotesProcessor:
    """Process startup quotes and essays from text files."""
    
    def __init__(self, source_dir: str = "data/source_material/startup quotes"):
        self.source_dir = Path(source_dir)
        if not self.source_dir.exists():
            raise ConfigurationError(f"Source directory not found: {source_dir}")
    
    def extract_text_from_file(self, file_path: Path) -> str:
        """Extract and clean text from a text file."""
        logger.info("Processing text file", file=str(file_path))
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            
            # Basic cleaning
            text = self.clean_text(text)
            
            logger.info("Text extraction complete", 
                       file=file_path.name,
                       total_chars=len(text))
            
            return text
            
        except Exception as e:
            logger.error("Failed to read text file", file=str(file_path), error=str(e))
            raise ConfigurationError(f"Could not process file {file_path}: {str(e)}")
    
    def clean_text(self, text: str) -> str:
        """Clean extracted text."""
        # Remove multiple newlines
        text = re.sub(r'\n\n+', '\n\n', text)
        
        # Fix spacing issues
        text = re.sub(r'\s+', ' ', text)
        
        # Ensure proper spacing after punctuation
        text = re.sub(r'([.!?])\s*([A-Z])', r'\1 \2', text)
        
        return text.strip()
    
    def process_all_files(self) -> List[Dict[str, str]]:
        """Process all text files in the source directory."""
        text_files = list(self.source_dir.glob("*.txt"))
        
        if not text_files:
            logger.warning("No text files found in source directory", dir=str(self.source_dir))
            return []
        
        logger.info("Processing startup quote files", count=len(text_files))
        
        processed_texts = []
        
        for text_path in text_files:
            try:
                # Skip empty or very small files
                if text_path.stat().st_size < 100:
                    logger.warning("Skipping small file", file=text_path.name)
                    continue
                
                # Extract and clean text
                text = self.extract_text_from_file(text_path)
                
                if len(text) < 100:  # Minimum viable content
                    logger.warning("Extracted text too short, skipping", 
                                 file=text_path.name, length=len(text))
                    continue
                
                # Create text record
                text_record = {
                    "filename": text_path.name,
                    "title": text_path.stem.replace('_', ' ').title(),
                    "text": text,
                    "word_count": len(text.split()),
                    "file_hash": self._get_file_hash(text_path)
                }
                
                processed_texts.append(text_record)
                logger.info("Successfully processed file", 
                           file=text_path.name, 
                           word_count=text_record["word_count"])
                
            except Exception as e:
                logger.error("Failed to process file", file=text_path.name, error=str(e))
                continue
        
        logger.info("Text processing complete", 
                   total_files=len(text_files),
                   successful=len(processed_texts))
        
        return processed_texts
    
    def _get_file_hash(self, file_path: Path) -> str:
        """Get MD5 hash of file for change detection."""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()


def process_startup_quotes_to_vectors():
    """Complete pipeline: Text files -> chunks -> embeddings -> vector DB."""
    logger.info("Starting startup quotes ingestion pipeline")
    
    # Step 1: Process text files
    processor = StartupQuotesProcessor()
    texts = processor.process_all_files()
    
    if not texts:
        logger.warning("No texts to process")
        return
    
    # Step 2: Chunk text (using smaller chunks for varied content)
    chunker = TextChunker(chunk_size=800, chunk_overlap=100)  # Smaller chunks for quotes
    
    all_chunks = []
    for text_data in texts:
        text_chunks = chunker.chunk_text(text_data["text"], text_data["title"])
        all_chunks.extend(text_chunks)
    
    logger.info("Text chunking complete", total_chunks=len(all_chunks))
    
    # Step 3: Generate embeddings
    embedding_generator = EmbeddingGenerator()
    embedded_chunks = embedding_generator.generate_embeddings(all_chunks)
    
    # Step 4: Store in vector database with custom collection name
    vector_manager = VectorDBManager()
    vector_manager.collection_name = "startup_knowledge"  # Override default collection
    stored_count = vector_manager.store_chunks(embedded_chunks)
    
    # Step 5: Show final stats
    stats = vector_manager.get_collection_stats()
    
    logger.info("Startup quotes ingestion pipeline complete",
               texts_processed=len(texts),
               chunks_created=len(all_chunks),
               chunks_stored=stored_count,
               **stats)
    
    print(f"\n✅ Startup Quotes Ingestion Complete!")
    print(f"📚 Files processed: {len(texts)}")
    print(f"📄 Chunks created: {len(all_chunks)}")
    print(f"💾 Chunks stored: {stored_count}")
    print(f"🎯 Unique sources: {stats['unique_sources']}")
    print(f"📊 Avg words/chunk: {stats['avg_words_per_chunk']}")
    
    return stats


def main():
    """Main function to run the startup quotes ingestion pipeline."""
    try:
        stats = process_startup_quotes_to_vectors()
        
        if stats and stats["total_chunks"] > 0:
            print(f"\n🚀 Startup quotes bot ready! Knowledge base contains {stats['total_chunks']} chunks from {stats['unique_sources']} sources.")
        else:
            print("\n❌ No content was ingested. Please check the 'data/source_material/startup quotes/' directory.")
    
    except Exception as e:
        logger.error("Startup quotes ingestion pipeline failed", error=str(e))
        print(f"\n❌ Ingestion failed: {str(e)}")
        raise


if __name__ == "__main__":
    main() 