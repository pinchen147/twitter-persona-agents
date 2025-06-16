"""
PDF ingestion module - Document processing and text extraction.

This module handles the first stage of the knowledge base pipeline: extracting
clean, usable text from PDF books. It implements sophisticated cleaning algorithms
to remove PDF artifacts while preserving the philosophical content.

Key Features:
- Robust PDF text extraction using pdfplumber
- Intelligent artifact removal (headers, footers, page numbers)
- OCR error correction and formatting fixes
- Minimum content validation
- File hash tracking for change detection

Cleaning Process:
1. Extract raw text from each PDF page
2. Detect and remove repeated headers/footers
3. Filter out page numbers and short fragments
4. Fix common OCR/extraction issues
5. Normalize whitespace and formatting

The processor ensures that only high-quality, readable text enters the
embedding pipeline, which is crucial for generating coherent tweets.
Books are processed from data/source_material/ directory.
"""

import re
import hashlib
from pathlib import Path
from typing import List, Dict, Optional
import pdfplumber
import structlog

from app.exceptions import ConfigurationError

logger = structlog.get_logger(__name__)


class PDFProcessor:
    """Process PDF files and extract clean text."""
    
    def __init__(self, source_dir: str = "data/source_material"):
        self.source_dir = Path(source_dir)
        self.source_dir.mkdir(parents=True, exist_ok=True)
    
    def extract_text_from_pdf(self, pdf_path: Path) -> str:
        """Extract text from a PDF file with cleanup."""
        logger.info("Extracting text from PDF", file=str(pdf_path))
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                full_text = ""
                page_texts = []
                
                for page_num, page in enumerate(pdf.pages, 1):
                    try:
                        text = page.extract_text()
                        if text:
                            page_texts.append(text)
                            logger.debug("Extracted text from page", page=page_num, chars=len(text))
                        else:
                            logger.warning("No text found on page", page=page_num)
                    except Exception as e:
                        logger.error("Failed to extract text from page", page=page_num, error=str(e))
                        continue
                
                full_text = "\n\n".join(page_texts)
                logger.info("PDF text extraction complete", 
                           total_pages=len(pdf.pages), 
                           extracted_pages=len(page_texts),
                           total_chars=len(full_text))
                
                return full_text
                
        except Exception as e:
            logger.error("Failed to open PDF file", file=str(pdf_path), error=str(e))
            raise ConfigurationError(f"Could not process PDF {pdf_path}: {str(e)}")
    
    def clean_text(self, text: str) -> str:
        """Clean extracted text by removing common PDF artifacts."""
        logger.debug("Starting text cleanup", original_length=len(text))
        
        # Split into lines for processing
        lines = text.split('\n')
        cleaned_lines = []
        
        # Track line patterns for header/footer detection
        line_frequencies = {}
        for line in lines:
            stripped = line.strip()
            if len(stripped) > 10:  # Only track substantial lines
                line_frequencies[stripped] = line_frequencies.get(stripped, 0) + 1
        
        # Identify repeated lines (likely headers/footers)
        repeated_lines = {line for line, count in line_frequencies.items() 
                         if count >= 3 and len(line) < 100}
        
        logger.debug("Found repeated lines for removal", count=len(repeated_lines))
        
        for line in lines:
            stripped = line.strip()
            
            # Skip empty lines
            if not stripped:
                continue
            
            # Skip repeated headers/footers
            if stripped in repeated_lines:
                continue
            
            # Skip lines that are mostly numbers (page numbers, etc.)
            if re.match(r'^[\d\s\-\.]+$', stripped):
                continue
            
            # Skip very short lines (likely artifacts)
            if len(stripped) < 3:
                continue
            
            # Skip lines with excessive punctuation/special characters
            if len(re.findall(r'[^\w\s]', stripped)) / len(stripped) > 0.3:
                continue
            
            cleaned_lines.append(stripped)
        
        # Join lines back together with proper spacing
        cleaned_text = ' '.join(cleaned_lines)
        
        # Additional cleanup
        cleaned_text = self._additional_cleanup(cleaned_text)
        
        logger.info("Text cleanup complete", 
                   original_length=len(text),
                   cleaned_length=len(cleaned_text),
                   reduction_percent=round((1 - len(cleaned_text)/len(text)) * 100, 1))
        
        return cleaned_text
    
    def _additional_cleanup(self, text: str) -> str:
        """Apply additional text cleanup patterns."""
        
        # Fix common OCR/extraction issues
        text = re.sub(r'\s+', ' ', text)  # Multiple spaces to single space
        text = re.sub(r'([.!?])\s*([A-Z])', r'\1 \2', text)  # Ensure space after punctuation
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)  # Add space between lowercase-uppercase
        
        # Remove common PDF artifacts
        text = re.sub(r'\b(Chapter|Page|Figure|Table)\s+\d+\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\b\d{1,3}\s*$', '', text, flags=re.MULTILINE)  # Page numbers at end of lines
        
        # Clean up whitespace again
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def process_all_pdfs(self) -> List[Dict[str, str]]:
        """Process all PDFs in the source directory."""
        pdf_files = list(self.source_dir.glob("*.pdf"))
        
        if not pdf_files:
            logger.warning("No PDF files found in source directory", dir=str(self.source_dir))
            return []
        
        logger.info("Processing PDF files", count=len(pdf_files))
        
        processed_books = []
        
        for pdf_path in pdf_files:
            try:
                # Extract and clean text
                raw_text = self.extract_text_from_pdf(pdf_path)
                cleaned_text = self.clean_text(raw_text)
                
                if len(cleaned_text) < 1000:  # Minimum viable book length
                    logger.warning("Extracted text too short, skipping", 
                                 file=pdf_path.name, length=len(cleaned_text))
                    continue
                
                # Create book record
                book_record = {
                    "filename": pdf_path.name,
                    "title": pdf_path.stem,  # Use filename without extension as title
                    "text": cleaned_text,
                    "word_count": len(cleaned_text.split()),
                    "file_hash": self._get_file_hash(pdf_path)
                }
                
                processed_books.append(book_record)
                logger.info("Successfully processed PDF", 
                           file=pdf_path.name, 
                           word_count=book_record["word_count"])
                
            except Exception as e:
                logger.error("Failed to process PDF", file=pdf_path.name, error=str(e))
                continue
        
        logger.info("PDF processing complete", 
                   total_files=len(pdf_files),
                   successful=len(processed_books))
        
        return processed_books
    
    def _get_file_hash(self, file_path: Path) -> str:
        """Get MD5 hash of file for change detection."""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()


def main():
    """Main function to run PDF ingestion."""
    processor = PDFProcessor()
    books = processor.process_all_pdfs()
    
    if books:
        print(f"Successfully processed {len(books)} books:")
        for book in books:
            print(f"  - {book['title']}: {book['word_count']:,} words")
        
        # Next step would be to chunk and embed these books
        print("\nNext: Run split_embed.py to chunk and create embeddings")
    else:
        print("No books were processed. Check that PDF files exist in data/source_material/")


if __name__ == "__main__":
    main()