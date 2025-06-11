"""Tweet generation engine for the Zen Kink Bot."""

import time
from pathlib import Path
from typing import Dict, List, Optional
import structlog
from jinja2 import Environment, FileSystemLoader
from openai import OpenAI

from app.deps import get_config, get_openai_client, get_persona, get_exemplars
from app.vector_search import get_random_seed_with_deduplication, get_generation_context
from app.monitoring import CostTracker, ActivityLogger
from app.exceptions import GenerationError, OpenAIError, CostLimitError

logger = structlog.get_logger(__name__)


class TweetGenerator:
    """Generate tweets using OpenAI API and context from vector database."""
    
    def __init__(self):
        self.openai_client = get_openai_client()
        self.cost_tracker = CostTracker()
        self.activity_logger = ActivityLogger()
        
        # Load configuration
        config = get_config()
        self.model = config.get("openai", {}).get("model", "o3")  # Default to o3 reasoning
        self.shortening_model = config.get("openai", {}).get("shortening_model", "gpt-4.1")
        self.max_tokens = config.get("openai", {}).get("max_tokens", 150)
        self.temperature = config.get("openai", {}).get("temperature", 0.8)
        self.character_limit = config.get("twitter", {}).get("character_limit", 280)
        
        # Setup Jinja2 for prompt templates
        self.jinja_env = Environment(
            loader=FileSystemLoader("prompts"),
            trim_blocks=True,
            lstrip_blocks=True
        )
        
    def check_cost_limits(self) -> bool:
        """Check if we're within cost limits before generating."""
        if not self.cost_tracker.check_daily_limit():
            daily_cost = self.cost_tracker.get_daily_cost()
            raise CostLimitError(f"Daily cost limit exceeded: ${daily_cost:.2f}")
        return True
    
    def build_generation_prompt(self, context_chunks: List[Dict[str, any]], 
                              exemplars: List[Dict[str, any]], 
                              persona: str) -> str:
        """Build the tweet generation prompt using Jinja2 template."""
        try:
            template = self.jinja_env.get_template("base_prompt.j2")
            
            prompt = template.render(
                persona=persona,
                context_chunks=context_chunks,
                exemplars=exemplars
            )
            
            logger.debug("Generation prompt built", 
                        prompt_length=len(prompt),
                        context_chunks_count=len(context_chunks),
                        exemplars_count=len(exemplars))
            
            return prompt
            
        except Exception as e:
            logger.error("Failed to build generation prompt", error=str(e))
            raise GenerationError(f"Failed to build prompt: {str(e)}")
    
    def call_openai_for_generation(self, prompt: str) -> str:
        """Call OpenAI API to generate tweet."""
        try:
            logger.debug("Calling OpenAI for tweet generation", model=self.model)
            
            start_time = time.time()
            
            # Check if using o3/o4 reasoning model - use Responses API
            if self.model.startswith(("o3", "o4")):
                # Use Responses API for reasoning models
                response = self.openai_client.responses.create(
                    model=self.model,
                    reasoning={"effort": "medium"},  # Medium reasoning effort for creative but focused tasks
                    input=[
                        {
                            "role": "system", 
                            "content": "You are a tweet generator that synthesizes philosophical wisdom into engaging social media content. Generate exactly one tweet. Do not include quotes, prefixes, or explanations. Just return the raw tweet text."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    max_output_tokens=300  # Reserve space for reasoning + output
                )
                # Extract tweet from response
                tweet_text = response.output_text.strip()
                
                # Get usage stats from reasoning model response
                usage = response.usage
                prompt_tokens = usage.input_tokens
                completion_tokens = usage.output_tokens
                total_tokens = usage.total_tokens
                reasoning_tokens = usage.output_tokens_details.get("reasoning_tokens", 0) if hasattr(usage, 'output_tokens_details') else 0
                
            else:
                # Use Chat Completions API for non-reasoning models (gpt-4o, etc.)
                response = self.openai_client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system", 
                            "content": "You are a tweet generator that synthesizes philosophical wisdom into engaging social media content. Generate exactly one tweet. Do not include quotes, prefixes, or explanations. Just return the raw tweet text."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=self.max_tokens,
                    temperature=self.temperature
                )
                # Extract tweet from chat completion
                tweet_text = response.choices[0].message.content.strip()
                
                # Get usage stats from chat completion
                usage = response.usage
                prompt_tokens = usage.prompt_tokens
                completion_tokens = usage.completion_tokens
                total_tokens = usage.total_tokens
                reasoning_tokens = 0
            api_time = time.time() - start_time
            
            # Remove quotes if they were added
            if (tweet_text.startswith('"') and tweet_text.endswith('"')) or \
               (tweet_text.startswith("'") and tweet_text.endswith("'")):
                tweet_text = tweet_text[1:-1]
            
            # Cost calculation based on model type
            if self.model.startswith(("o3", "o4")):
                # o3/o4 reasoning models - note: all output tokens (including reasoning) are billed
                # Approximate pricing - update with actual pricing when available
                if "mini" in self.model.lower():
                    cost = (prompt_tokens * 0.0015 + completion_tokens * 0.006) / 1000
                else:
                    cost = (prompt_tokens * 0.06 + completion_tokens * 0.24) / 1000  # Full o3/o4 pricing
            elif "gpt-4o" in self.model.lower():
                # GPT-4o pricing
                cost = (prompt_tokens * 0.0025 + completion_tokens * 0.01) / 1000
            elif "gpt-4" in self.model.lower():
                # GPT-4 pricing
                cost = (prompt_tokens * 0.03 + completion_tokens * 0.06) / 1000
            else:  # GPT-3.5-turbo or other
                cost = (prompt_tokens * 0.0015 + completion_tokens * 0.002) / 1000
            
            self.cost_tracker.record_cost(
                service="openai",
                operation="completion",
                cost_usd=cost,
                tokens_used=total_tokens,
                metadata={
                    "model": self.model,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "reasoning_tokens": reasoning_tokens,
                    "api_time_ms": int(api_time * 1000)
                }
            )
            
            logger.info("Tweet generated successfully", 
                       model=self.model,
                       tokens_used=total_tokens,
                       reasoning_tokens=reasoning_tokens,
                       cost_usd=cost,
                       tweet_length=len(tweet_text),
                       api_time_ms=int(api_time * 1000))
            
            return tweet_text
            
        except Exception as e:
            logger.error("OpenAI generation failed", model=self.model, error=str(e))
            raise OpenAIError(f"Tweet generation failed: {str(e)}")
    
    def shorten_tweet_if_needed(self, tweet_text: str) -> str:
        """Shorten tweet if it exceeds character limit."""
        if len(tweet_text) <= self.character_limit:
            return tweet_text
        
        logger.info("Tweet too long, attempting to shorten", 
                   original_length=len(tweet_text),
                   limit=self.character_limit)
        
        try:
            # Build shortening prompt
            template = self.jinja_env.get_template("shortening_prompt.j2")
            shortening_prompt = template.render(
                tweet_text=tweet_text,
                current_length=len(tweet_text),
                target_length=self.character_limit - 10  # Leave some buffer
            )
            
            # Call OpenAI for shortening
            start_time = time.time()
            response = self.openai_client.chat.completions.create(
                model=self.shortening_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a text editor. Shorten the given text while preserving its core message. Return only the shortened text."
                    },
                    {"role": "user", "content": shortening_prompt}
                ],
                max_tokens=100,
                temperature=0.3  # Lower temperature for more focused editing
            )
            api_time = time.time() - start_time
            
            shortened_text = response.choices[0].message.content.strip()
            
            # Remove quotes if added
            if (shortened_text.startswith('"') and shortened_text.endswith('"')) or \
               (shortened_text.startswith("'") and shortened_text.endswith("'")):
                shortened_text = shortened_text[1:-1]
            
            # Record cost based on shortening model
            total_tokens = response.usage.total_tokens
            if "gpt-4o" in self.shortening_model.lower():
                cost = (response.usage.prompt_tokens * 0.0025 + response.usage.completion_tokens * 0.01) / 1000
            else:  # GPT-3.5-turbo or other
                cost = total_tokens * 0.002 / 1000
            
            self.cost_tracker.record_cost(
                service="openai",
                operation="shortening",
                cost_usd=cost,
                tokens_used=total_tokens,
                metadata={
                    "model": self.shortening_model,
                    "original_length": len(tweet_text),
                    "shortened_length": len(shortened_text),
                    "api_time_ms": int(api_time * 1000)
                }
            )
            
            logger.info("Tweet shortened successfully",
                       original_length=len(tweet_text),
                       shortened_length=len(shortened_text),
                       cost_usd=cost)
            
            return shortened_text
            
        except Exception as e:
            logger.error("Tweet shortening failed", error=str(e))
            # If shortening fails, truncate manually as fallback
            truncated = tweet_text[:self.character_limit-3] + "..."
            logger.warning("Fell back to manual truncation", truncated_length=len(truncated))
            return truncated
    
    def generate_tweet(self, test_mode: bool = False) -> Dict[str, any]:
        """Generate a complete tweet with context and persona."""
        generation_start = time.time()
        
        try:
            # Check cost limits
            self.check_cost_limits()
            
            # Step 1: Get random seed chunk with deduplication
            logger.info("Starting tweet generation")
            seed_chunk, seed_hash = get_random_seed_with_deduplication()
            
            # Step 2: Get context chunks
            context_chunks = get_generation_context(seed_chunk)
            
            # Step 3: Load persona and exemplars
            persona = get_persona()
            exemplars = get_exemplars()
            
            # Step 4: Build prompt
            prompt = self.build_generation_prompt(context_chunks, exemplars, persona)
            
            # Step 5: Generate tweet
            tweet_text = self.call_openai_for_generation(prompt)
            
            # Step 6: Check and shorten if needed
            final_tweet = self.shorten_tweet_if_needed(tweet_text)
            
            generation_time = int((time.time() - generation_start) * 1000)
            
            result = {
                "tweet_text": final_tweet,
                "seed_chunk_hash": seed_hash,
                "seed_chunk_id": seed_chunk["id"],
                "seed_source": seed_chunk["metadata"].get("source_title", "Unknown"),
                "context_chunks_count": len(context_chunks),
                "character_count": len(final_tweet),
                "generation_time_ms": generation_time,
                "was_shortened": len(tweet_text) != len(final_tweet),
                "test_mode": test_mode
            }
            
            logger.info("Tweet generation complete", **result)
            
            return result
            
        except Exception as e:
            generation_time = int((time.time() - generation_start) * 1000)
            logger.error("Tweet generation failed", 
                        error=str(e),
                        generation_time_ms=generation_time)
            
            # Log the failed attempt
            self.activity_logger.log_post_attempt(
                tweet_text="",
                seed_chunk_hash="",
                status="generation_failed",
                error_message=str(e),
                generation_time_ms=generation_time
            )
            
            raise GenerationError(f"Tweet generation failed: {str(e)}")


async def generate_and_post_tweet() -> Dict[str, any]:
    """Generate and post a tweet (main entry point)."""
    from app.twitter_client import TwitterPoster
    from app.security import ContentFilter
    
    generator = TweetGenerator()
    
    try:
        # Generate tweet
        generation_result = generator.generate_tweet()
        
        # Filter content
        content_filter = ContentFilter()
        if not content_filter.is_content_safe(generation_result["tweet_text"]):
            raise GenerationError("Generated content failed safety filters")
        
        # Post to Twitter
        twitter_poster = TwitterPoster()
        post_result = await twitter_poster.post_tweet(generation_result["tweet_text"])
        
        # Log successful post
        generator.activity_logger.log_post_attempt(
            tweet_text=generation_result["tweet_text"],
            seed_chunk_hash=generation_result["seed_chunk_hash"],
            status="success",
            twitter_id=post_result.get("twitter_id"),
            generation_time_ms=generation_result["generation_time_ms"],
            metadata={
                "seed_source": generation_result["seed_source"],
                "was_shortened": generation_result["was_shortened"],
                "character_count": generation_result["character_count"]
            }
        )
        
        return {
            **generation_result,
            **post_result,
            "status": "success"
        }
        
    except Exception as e:
        logger.error("Generate and post failed", error=str(e))
        return {
            "status": "failed",
            "error": str(e)
        }


async def generate_test_tweet(custom_persona: Optional[str] = None) -> Dict[str, any]:
    """Generate a test tweet without posting."""
    generator = TweetGenerator()
    
    try:
        # Override persona if provided
        if custom_persona:
            original_get_persona = get_persona
            def mock_get_persona():
                return custom_persona
            
            # Temporarily replace the function
            import app.deps
            app.deps.get_persona = mock_get_persona
            
            try:
                result = generator.generate_tweet(test_mode=True)
            finally:
                # Restore original function
                app.deps.get_persona = original_get_persona
        else:
            result = generator.generate_tweet(test_mode=True)
        
        return {
            **result,
            "status": "success"
        }
        
    except Exception as e:
        logger.error("Test tweet generation failed", error=str(e))
        return {
            "status": "failed",
            "error": str(e)
        }