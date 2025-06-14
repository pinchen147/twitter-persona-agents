"""Vector search operations for the Zen Kink Bot."""

import random
from typing import List, Dict, Optional, Tuple
import structlog
from openai import OpenAI

from app.deps import get_vector_db, get_config, get_openai_client, get_vector_collection_name
from app.monitoring import ActivityLogger
from app.exceptions import VectorDBError, OpenAIError

logger = structlog.get_logger(__name__)


class VectorSearcher:
    """Handle vector database search operations."""
    
    def __init__(self, account_id: str = None, collection_name: str = None):
        self.client = get_vector_db()
        self.openai_client = get_openai_client()
        self.activity_logger = ActivityLogger()
        self.account_id = account_id
        
        config = get_config()
        
        # Determine collection name
        if collection_name:
            self.collection_name = collection_name
        elif account_id:
            self.collection_name = get_vector_collection_name(account_id)
        else:
            # Fallback to config default
            self.collection_name = config.get("vector_db", {}).get("collection_name", "zen_kink_knowledge")
        
        self.embedding_model = config.get("openai", {}).get("embedding_model", "text-embedding-3-small")
        self.similarity_threshold = config.get("text_processing", {}).get("similarity_threshold", 0.7)
        
        self.collection = None
        self._get_collection()
    
    def _get_collection(self):
        """Get the vector database collection."""
        try:
            self.collection = self.client.get_collection(name=self.collection_name)
            logger.debug("Connected to vector collection", name=self.collection_name)
        except Exception as e:
            logger.error("Failed to get vector collection", error=str(e))
            raise VectorDBError(f"Cannot access collection {self.collection_name}: {str(e)}")
    
    def get_random_seed_chunk(self, exclude_hashes: Optional[List[str]] = None) -> Dict[str, any]:
        """Get a random chunk to use as generation seed."""
        try:
            # Get total count
            total_count = self.collection.count()
            if total_count == 0:
                raise VectorDBError("No chunks available in vector database")
            
            max_attempts = 10
            for attempt in range(max_attempts):
                # Get random offset
                random_offset = random.randint(0, total_count - 1)
                
                # Get chunk at random position
                result = self.collection.get(
                    limit=1,
                    offset=random_offset,
                    include=["documents", "metadatas"]
                )
                
                if not result["documents"]:
                    continue
                
                chunk = {
                    "id": result["ids"][0],
                    "text": result["documents"][0],
                    "metadata": result["metadatas"][0]
                }
                
                # Check if we should exclude this chunk (for deduplication)
                chunk_hash = chunk["metadata"].get("chunk_hash")
                if exclude_hashes and chunk_hash in exclude_hashes:
                    logger.debug("Skipping recently used chunk", 
                               chunk_hash=chunk_hash, 
                               attempt=attempt + 1)
                    continue
                
                logger.info("Selected random seed chunk", 
                           chunk_id=chunk["id"],
                           source=chunk["metadata"].get("source_title"),
                           chunk_hash=chunk_hash)
                
                return chunk
            
            # If we couldn't find a non-excluded chunk, just return a random one
            logger.warning("Could not find non-excluded chunk, using random chunk anyway")
            random_offset = random.randint(0, total_count - 1)
            result = self.collection.get(
                limit=1,
                offset=random_offset,
                include=["documents", "metadatas"]
            )
            
            return {
                "id": result["ids"][0],
                "text": result["documents"][0],
                "metadata": result["metadatas"][0]
            }
            
        except Exception as e:
            logger.error("Failed to get random seed chunk", error=str(e))
            raise VectorDBError(f"Failed to get random seed: {str(e)}")
    
    def find_similar_chunks(self, query_text: str, n_results: int = 5, 
                          exclude_id: Optional[str] = None) -> List[Dict[str, any]]:
        """Find chunks similar to the query text using vector search."""
        try:
            # Generate embedding for query
            logger.debug("Generating embedding for similarity search", query_length=len(query_text))
            
            embedding_response = self.openai_client.embeddings.create(
                input=query_text,
                model=self.embedding_model
            )
            query_embedding = embedding_response.data[0].embedding
            
            # Perform vector search
            search_results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results + (1 if exclude_id else 0),  # Get extra in case we need to exclude
                include=["documents", "metadatas", "distances"]
            )
            
            # Process results
            similar_chunks = []
            for i, (doc, metadata, distance) in enumerate(zip(
                search_results["documents"][0],
                search_results["metadatas"][0], 
                search_results["distances"][0]
            )):
                chunk_id = search_results["ids"][0][i]
                
                # Skip excluded chunk
                if exclude_id and chunk_id == exclude_id:
                    continue
                
                # Check similarity threshold
                similarity = 1 - distance  # Convert distance to similarity
                if similarity < self.similarity_threshold:
                    logger.debug("Chunk below similarity threshold", 
                               chunk_id=chunk_id, 
                               similarity=similarity,
                               threshold=self.similarity_threshold)
                    continue
                
                chunk = {
                    "id": chunk_id,
                    "text": doc,
                    "metadata": metadata,
                    "similarity": similarity,
                    "distance": distance
                }
                
                similar_chunks.append(chunk)
                
                # Stop if we have enough results
                if len(similar_chunks) >= n_results:
                    break
            
            logger.info("Similarity search complete", 
                       query_length=len(query_text),
                       results_found=len(similar_chunks),
                       avg_similarity=sum(c["similarity"] for c in similar_chunks) / len(similar_chunks) if similar_chunks else 0)
            
            return similar_chunks
            
        except Exception as e:
            logger.error("Similarity search failed", error=str(e))
            raise VectorDBError(f"Similarity search failed: {str(e)}")
    
    def search_chunks_by_text(self, query: str, limit: int = 10) -> List[Dict[str, any]]:
        """Search chunks by text content (for UI search functionality)."""
        try:
            # For text search, we'll use embedding-based search
            embedding_response = self.openai_client.embeddings.create(
                input=query,
                model=self.embedding_model
            )
            query_embedding = embedding_response.data[0].embedding
            
            # Search with embedding
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=limit,
                include=["documents", "metadatas", "distances"]
            )
            
            # Format results for UI
            search_results = []
            for i, (doc, metadata, distance) in enumerate(zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0]
            )):
                similarity = 1 - distance
                
                result = {
                    "id": results["ids"][0][i],
                    "text": doc[:200] + "..." if len(doc) > 200 else doc,  # Truncate for UI
                    "full_text": doc,
                    "source_title": metadata.get("source_title", "Unknown"),
                    "chunk_index": metadata.get("chunk_index", 0),
                    "word_count": metadata.get("word_count", 0),
                    "similarity": round(similarity, 3)
                }
                
                search_results.append(result)
            
            logger.debug("Text search complete", 
                        query=query,
                        results_count=len(search_results))
            
            return search_results
            
        except Exception as e:
            logger.error("Text search failed", query=query, error=str(e))
            raise VectorDBError(f"Text search failed: {str(e)}")
    
    def get_context_for_generation(self, seed_chunk: Dict[str, any], 
                                 context_size: int = 3) -> List[Dict[str, any]]:
        """Get context chunks for tweet generation based on seed chunk."""
        try:
            # Find similar chunks to the seed
            similar_chunks = self.find_similar_chunks(
                query_text=seed_chunk["text"],
                n_results=context_size,
                exclude_id=seed_chunk["id"]
            )
            
            # Include the seed chunk itself
            context_chunks = [seed_chunk] + similar_chunks[:context_size]
            
            logger.info("Generated context for tweet generation",
                       seed_chunk_id=seed_chunk["id"],
                       context_size=len(context_chunks),
                       avg_similarity=sum(c.get("similarity", 1.0) for c in context_chunks[1:]) / max(1, len(context_chunks) - 1))
            
            return context_chunks
            
        except Exception as e:
            logger.error("Failed to get context for generation", 
                        seed_chunk_id=seed_chunk.get("id"),
                        error=str(e))
            raise VectorDBError(f"Failed to get generation context: {str(e)}")
    
    def get_collection_info(self) -> Dict[str, any]:
        """Get information about the vector collection."""
        try:
            count = self.collection.count()
            
            if count == 0:
                return {
                    "total_chunks": 0,
                    "sources": [],
                    "sample_chunks": []
                }
            
            # Get sample of chunks to analyze
            sample_size = min(50, count)
            sample_results = self.collection.get(
                limit=sample_size,
                include=["documents", "metadatas"]
            )
            
            # Analyze sources
            sources = set()
            for metadata in sample_results["metadatas"]:
                sources.add(metadata.get("source_title", "Unknown"))
            
            # Get sample chunks for display
            sample_chunks = []
            for i, (doc, metadata) in enumerate(zip(
                sample_results["documents"][:5],  # Just first 5 for display
                sample_results["metadatas"][:5]
            )):
                sample_chunks.append({
                    "id": sample_results["ids"][i],
                    "text": doc[:150] + "..." if len(doc) > 150 else doc,
                    "source_title": metadata.get("source_title", "Unknown"),
                    "chunk_index": metadata.get("chunk_index", 0)
                })
            
            return {
                "total_chunks": count,
                "sources": sorted(list(sources)),
                "sample_chunks": sample_chunks
            }
            
        except Exception as e:
            logger.error("Failed to get collection info", error=str(e))
            raise VectorDBError(f"Failed to get collection info: {str(e)}")


# Convenience functions for use in other modules
def get_random_seed_with_deduplication(account_id: str = None) -> Tuple[Dict[str, any], str]:
    """Get random seed chunk with deduplication check."""
    searcher = VectorSearcher(account_id=account_id)
    activity_logger = ActivityLogger()
    
    # Get recent seed hashes for deduplication
    config = get_config()
    lookback_count = config.get("deduplication", {}).get("recent_posts_lookback", 50)
    recent_hashes = activity_logger.get_recent_seed_hashes(limit=lookback_count)
    
    # Get random seed chunk
    seed_chunk = searcher.get_random_seed_chunk(exclude_hashes=recent_hashes)
    seed_hash = seed_chunk["metadata"].get("chunk_hash", "unknown")
    
    return seed_chunk, seed_hash


def get_generation_context(seed_chunk: Dict[str, any], account_id: str = None) -> List[Dict[str, any]]:
    """Get context chunks for generation."""
    searcher = VectorSearcher(account_id=account_id)
    return searcher.get_context_for_generation(seed_chunk)


def search_knowledge_base(query: str, limit: int = 10, account_id: str = None) -> List[Dict[str, any]]:
    """Search the knowledge base (for UI)."""
    searcher = VectorSearcher(account_id=account_id)
    return searcher.search_chunks_by_text(query, limit=limit)