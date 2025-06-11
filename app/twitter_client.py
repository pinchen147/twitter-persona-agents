"""Twitter API client for the Zen Kink Bot."""

import time
from typing import Dict, List, Optional
import structlog
import tweepy

from app.deps import get_config, get_twitter_client
from app.monitoring import CostTracker, ActivityLogger
from app.exceptions import TwitterError

logger = structlog.get_logger(__name__)


class TwitterPoster:
    """Handle Twitter posting operations with rate limiting and error handling."""
    
    def __init__(self):
        self.client = get_twitter_client()
        self.activity_logger = ActivityLogger()
        
        # Load configuration
        config = get_config()
        self.post_enabled = config.get("twitter", {}).get("post_enabled", True)
        self.character_limit = config.get("twitter", {}).get("character_limit", 280)
        
        # Rate limiting tracking
        self.last_post_time = 0
        self.min_interval_seconds = 60  # Minimum 1 minute between posts
    
    def validate_tweet(self, tweet_text: str) -> bool:
        """Validate tweet meets Twitter requirements."""
        if not tweet_text or not tweet_text.strip():
            raise TwitterError("Tweet text is empty")
        
        if len(tweet_text) > self.character_limit:
            raise TwitterError(f"Tweet too long: {len(tweet_text)} > {self.character_limit}")
        
        # Check for basic content issues
        if tweet_text.strip() == "":
            raise TwitterError("Tweet contains only whitespace")
        
        return True
    
    def check_rate_limits(self) -> bool:
        """Check if we can post without hitting rate limits."""
        current_time = time.time()
        
        # Check minimum interval
        if current_time - self.last_post_time < self.min_interval_seconds:
            wait_time = self.min_interval_seconds - (current_time - self.last_post_time)
            raise TwitterError(f"Rate limit: must wait {wait_time:.1f} more seconds")
        
        return True
    
    async def post_tweet(self, tweet_text: str) -> Dict[str, any]:
        """Post a tweet to Twitter with comprehensive error handling."""
        logger.info("Attempting to post tweet", 
                   character_count=len(tweet_text),
                   post_enabled=self.post_enabled)
        
        try:
            # Validate tweet
            self.validate_tweet(tweet_text)
            
            # Check if posting is enabled
            if not self.post_enabled:
                logger.info("Tweet posting disabled in config, simulating post")
                return {
                    "twitter_id": "simulated_12345",
                    "status": "simulated",
                    "message": "Tweet posting disabled - this was a simulation",
                    "url": "https://twitter.com/simulated",
                    "posted_at": time.time()
                }
            
            # Check rate limits
            self.check_rate_limits()
            
            # Attempt to post
            start_time = time.time()
            
            try:
                response = self.client.create_tweet(text=tweet_text)
                post_time = time.time()
                api_time = int((post_time - start_time) * 1000)
                
                # Update rate limiting
                self.last_post_time = post_time
                
                # Extract tweet information
                tweet_id = response.data['id']
                twitter_url = f"https://twitter.com/user/status/{tweet_id}"
                
                logger.info("Tweet posted successfully", 
                           tweet_id=tweet_id,
                           character_count=len(tweet_text),
                           api_time_ms=api_time)
                
                # Log to activity logger
                self.activity_logger.log_system_event(
                    event_type="tweet_posted",
                    message=f"Successfully posted tweet {tweet_id}",
                    level="INFO",
                    metadata={
                        "tweet_id": tweet_id,
                        "character_count": len(tweet_text),
                        "api_time_ms": api_time
                    }
                )
                
                return {
                    "twitter_id": tweet_id,
                    "status": "posted",
                    "message": "Tweet posted successfully",
                    "url": twitter_url,
                    "posted_at": post_time,
                    "api_time_ms": api_time
                }
                
            except tweepy.TooManyRequests as e:
                logger.warning("Twitter rate limit hit", error=str(e))
                
                # Extract rate limit reset time if available
                reset_time = getattr(e.response, 'headers', {}).get('x-rate-limit-reset', None)
                if reset_time:
                    wait_time = int(reset_time) - int(time.time())
                    raise TwitterError(f"Rate limit exceeded. Reset in {wait_time} seconds.")
                else:
                    raise TwitterError("Rate limit exceeded. Try again later.")
            
            except tweepy.Forbidden as e:
                logger.error("Twitter API forbidden error", error=str(e))
                raise TwitterError(f"Tweet rejected by Twitter: {str(e)}")
            
            except tweepy.BadRequest as e:
                logger.error("Twitter API bad request", error=str(e))
                raise TwitterError(f"Invalid tweet content: {str(e)}")
            
            except tweepy.Unauthorized as e:
                logger.error("Twitter API unauthorized", error=str(e))
                raise TwitterError(f"Twitter authentication failed: {str(e)}")
            
            except Exception as e:
                logger.error("Unexpected Twitter API error", error=str(e), error_type=type(e).__name__)
                raise TwitterError(f"Unexpected Twitter error: {str(e)}")
                
        except TwitterError:
            # Re-raise TwitterError as-is
            raise
        except Exception as e:
            logger.error("Unexpected error in post_tweet", error=str(e))
            raise TwitterError(f"Unexpected posting error: {str(e)}")
    
    def get_account_info(self) -> Dict[str, any]:
        """Get information about the connected Twitter account."""
        try:
            # Get authenticated user info
            user = self.client.get_me(user_fields=["public_metrics", "created_at", "description"])
            
            if user.data:
                user_data = user.data
                metrics = user_data.public_metrics or {}
                
                return {
                    "user_id": user_data.id,
                    "username": user_data.username,
                    "name": user_data.name,
                    "description": user_data.description,
                    "followers_count": metrics.get("followers_count", 0),
                    "following_count": metrics.get("following_count", 0),
                    "tweet_count": metrics.get("tweet_count", 0),
                    "listed_count": metrics.get("listed_count", 0),
                    "created_at": str(user_data.created_at) if user_data.created_at else None
                }
            else:
                raise TwitterError("Could not retrieve user information")
                
        except Exception as e:
            logger.error("Failed to get account info", error=str(e))
            raise TwitterError(f"Failed to get account info: {str(e)}")
    
    def get_recent_tweets(self, count: int = 5) -> List[Dict[str, any]]:
        """Get recent tweets from the authenticated account."""
        try:
            # Get authenticated user first
            me = self.client.get_me()
            if not me.data:
                raise TwitterError("Could not get authenticated user")
            
            user_id = me.data.id
            
            # Get recent tweets
            tweets = self.client.get_users_tweets(
                id=user_id,
                max_results=min(count, 100),  # Twitter API limit
                tweet_fields=["created_at", "public_metrics", "context_annotations"]
            )
            
            if not tweets.data:
                return []
            
            recent_tweets = []
            for tweet in tweets.data:
                metrics = tweet.public_metrics or {}
                
                tweet_info = {
                    "id": tweet.id,
                    "text": tweet.text,
                    "created_at": str(tweet.created_at) if tweet.created_at else None,
                    "retweet_count": metrics.get("retweet_count", 0),
                    "like_count": metrics.get("like_count", 0),
                    "reply_count": metrics.get("reply_count", 0),
                    "quote_count": metrics.get("quote_count", 0),
                    "url": f"https://twitter.com/user/status/{tweet.id}"
                }
                
                recent_tweets.append(tweet_info)
            
            logger.info("Retrieved recent tweets", count=len(recent_tweets))
            return recent_tweets
            
        except Exception as e:
            logger.error("Failed to get recent tweets", error=str(e))
            raise TwitterError(f"Failed to get recent tweets: {str(e)}")
    
    def test_connection(self) -> bool:
        """Test Twitter API connection and authentication."""
        try:
            user = self.client.get_me()
            if user.data:
                logger.info("Twitter connection test successful", 
                           username=user.data.username)
                return True
            else:
                logger.error("Twitter connection test failed - no user data")
                return False
                
        except Exception as e:
            logger.error("Twitter connection test failed", error=str(e))
            return False


# Convenience functions for use in other modules
async def post_tweet_simple(tweet_text: str) -> bool:
    """Simple tweet posting function that returns success/failure."""
    try:
        poster = TwitterPoster()
        result = await poster.post_tweet(tweet_text)
        return result["status"] in ["posted", "simulated"]
    except Exception as e:
        logger.error("Simple tweet posting failed", error=str(e))
        return False


def test_twitter_connection() -> bool:
    """Test Twitter API connection."""
    try:
        poster = TwitterPoster()
        return poster.test_connection()
    except Exception:
        return False


def get_twitter_account_info() -> Optional[Dict[str, any]]:
    """Get Twitter account information."""
    try:
        poster = TwitterPoster()
        return poster.get_account_info()
    except Exception as e:
        logger.error("Failed to get Twitter account info", error=str(e))
        return None