"""
Threads API client - Platform integration and posting management for Meta's Threads.

This module handles all interactions with the Threads API, providing a robust
interface for posting threads, retrieving account information, and managing rate limits.
It supports multi-account operations with account-specific credentials.

Key Features:
- Threads API integration using HTTP requests
- Account-specific client instances
- Comprehensive error handling with retry logic
- Rate limit management and tracking
- Test mode for development without posting
- Thread validation and metrics retrieval

Architecture:
- Uses HTTP requests for Threads API interactions
- Each account gets its own authenticated client
- Credentials loaded from account JSON files
- Built-in rate limiting (1 minute between posts)

Error Handling:
- Rate limit tracking and waiting
- Content policy violations
- Invalid thread format
- Authentication failures

The module ensures reliable Threads posting with proper error handling,
rate limit compliance, and comprehensive logging for debugging.
"""

import json
import time
from typing import Dict, List, Optional

import httpx
import structlog

from app.deps import get_config
from app.exceptions import ZenKinkBotException
from app.monitoring import ActivityLogger

logger = structlog.get_logger(__name__)


class ThreadsError(ZenKinkBotException):
    """Custom exception for Threads API errors."""

    pass


class ThreadsPoster:
    """Handle Threads posting operations with rate limiting and error handling."""

    def __init__(self, account_id: str = None):
        self.account_id = account_id
        self.activity_logger = ActivityLogger()

        # Load configuration
        config = get_config()
        self.post_enabled = config.get("threads", {}).get("post_enabled", True)
        self.character_limit = config.get("threads", {}).get("character_limit", 500)

        # Load account-specific credentials
        if account_id:
            from app.account_manager import get_account

            account = get_account(account_id)
            if not account:
                raise ThreadsError(f"Account {account_id} not found")

            threads_creds = account.get("threads_credentials", {})
            self.access_token = threads_creds.get("access_token")
            self.user_id = threads_creds.get("user_id")

            if not self.access_token or not self.user_id:
                raise ThreadsError(
                    f"Missing Threads credentials for account {account_id}"
                )
        else:
            raise ThreadsError("Account ID is required for Threads posting")

        # Threads API endpoints
        self.base_url = "https://graph.threads.net"

        # Rate limiting tracking
        self.last_post_time = 0
        self.min_interval_seconds = 60  # Minimum 1 minute between posts

        # HTTP client with timeout configuration
        self.client = httpx.Client(timeout=30.0)

    def validate_thread(self, thread_text: str) -> bool:
        """Validate thread meets Threads requirements."""
        if not thread_text or not thread_text.strip():
            raise ThreadsError("Thread text is empty")

        if len(thread_text) > self.character_limit:
            raise ThreadsError(
                f"Thread too long: {len(thread_text)} > {self.character_limit}"
            )

        # Check for basic content issues
        if thread_text.strip() == "":
            raise ThreadsError("Thread contains only whitespace")

        return True

    def check_rate_limits(self) -> bool:
        """Check if we can post without hitting rate limits."""
        current_time = time.time()

        # Check minimum interval
        if current_time - self.last_post_time < self.min_interval_seconds:
            wait_time = self.min_interval_seconds - (current_time - self.last_post_time)
            raise ThreadsError(f"Rate limit: must wait {wait_time:.1f} more seconds")

        return True

    async def post_thread(self, thread_text: str) -> Dict[str, any]:
        """Post a thread to Threads with comprehensive error handling."""
        logger.info(
            "Attempting to post thread",
            character_count=len(thread_text),
            post_enabled=self.post_enabled,
            account_id=self.account_id,
        )

        try:
            # Validate thread
            self.validate_thread(thread_text)

            # Check if posting is enabled
            if not self.post_enabled:
                logger.info("Thread posting disabled in config, simulating post")
                return {
                    "threads_id": "simulated_12345",
                    "status": "simulated",
                    "message": "Thread posting disabled - this was a simulation",
                    "url": "https://threads.net/simulated",
                    "posted_at": time.time(),
                }

            # Check rate limits
            self.check_rate_limits()

            # Attempt to post
            start_time = time.time()

            try:
                # Step 1: Create media container
                create_url = f"{self.base_url}/v1.0/{self.user_id}/threads"
                create_data = {
                    "media_type": "TEXT",
                    "text": thread_text,
                    "access_token": self.access_token,
                }

                logger.debug("Creating Threads media container", url=create_url)
                create_response = self.client.post(create_url, data=create_data)
                create_response.raise_for_status()
                create_result = create_response.json()

                if "id" not in create_result:
                    raise ThreadsError(
                        "Failed to create media container - no ID returned"
                    )

                container_id = create_result["id"]
                logger.debug("Media container created", container_id=container_id)

                # Step 2: Publish the thread
                publish_url = f"{self.base_url}/v1.0/{self.user_id}/threads_publish"
                publish_data = {
                    "creation_id": container_id,
                    "access_token": self.access_token,
                }

                logger.debug("Publishing thread", container_id=container_id)
                publish_response = self.client.post(publish_url, data=publish_data)
                publish_response.raise_for_status()
                publish_result = publish_response.json()

                post_time = time.time()
                api_time = int((post_time - start_time) * 1000)

                # Update rate limiting
                self.last_post_time = post_time

                # Extract thread information
                thread_id = publish_result.get("id", container_id)
                threads_url = f"https://threads.net/@{self.account_id}/post/{thread_id}"

                logger.info(
                    "Thread posted successfully",
                    thread_id=thread_id,
                    character_count=len(thread_text),
                    api_time_ms=api_time,
                    account_id=self.account_id,
                )

                # Log to activity logger
                self.activity_logger.log_system_event(
                    event_type="thread_posted",
                    message=f"Successfully posted thread {thread_id} for account {self.account_id}",
                    level="INFO",
                    metadata={
                        "thread_id": thread_id,
                        "character_count": len(thread_text),
                        "api_time_ms": api_time,
                        "account_id": self.account_id,
                        "platform": "threads",
                    },
                )

                return {
                    "threads_id": thread_id,
                    "status": "posted",
                    "message": "Thread posted successfully",
                    "url": threads_url,
                    "posted_at": post_time,
                    "api_time_ms": api_time,
                }

            except httpx.ReadTimeout as e:
                logger.error(
                    "Threads API timeout",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                raise ThreadsError("Request timeout - Threads API is not responding")
                
            except httpx.ConnectTimeout as e:
                logger.error(
                    "Threads API connection timeout",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                raise ThreadsError("Connection timeout - Unable to reach Threads API")
                
            except httpx.HTTPError as e:
                response_text = ""
                status_code = None
                
                # Handle different types of HTTP errors
                if hasattr(e, "response") and e.response:
                    status_code = e.response.status_code
                    try:
                        response_data = e.response.json()
                        response_text = json.dumps(response_data, indent=2)
                    except:
                        response_text = e.response.text

                logger.error(
                    "Threads API HTTP error",
                    error=str(e),
                    error_type=type(e).__name__,
                    status_code=status_code,
                    response=response_text,
                )

                # Handle specific HTTP status codes
                if status_code:
                    if status_code == 429:
                        raise ThreadsError("Rate limit exceeded. Try again later.")
                    elif status_code == 403:
                        raise ThreadsError(
                            f"Thread rejected by Threads: {response_text}"
                        )
                    elif status_code == 400:
                        raise ThreadsError(f"Invalid thread content: {response_text}")
                    elif status_code == 401:
                        raise ThreadsError(
                            f"Threads authentication failed: {response_text}"
                        )
                    else:
                        raise ThreadsError(
                            f"Threads API error ({status_code}): {response_text}"
                        )
                else:
                    # Handle timeout and connection errors that don't have response
                    if "timeout" in str(e).lower():
                        raise ThreadsError("Request timeout - Threads API is not responding")
                    elif "connection" in str(e).lower():
                        raise ThreadsError("Connection error - Unable to reach Threads API")
                    else:
                        raise ThreadsError(f"Threads API error: {str(e)}")

            except Exception as e:
                logger.error(
                    "Unexpected Threads API error",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                raise ThreadsError(f"Unexpected Threads error: {str(e)}")

        except ThreadsError:
            # Re-raise ThreadsError as-is
            raise
        except Exception as e:
            logger.error("Unexpected error in post_thread", error=str(e))
            raise ThreadsError(f"Unexpected posting error: {str(e)}")

    def get_account_info(self) -> Dict[str, any]:
        """Get information about the connected Threads account."""
        try:
            url = f"{self.base_url}/v1.0/{self.user_id}"
            params = {
                "fields": "id,username,name,threads_profile_picture_url,threads_biography",
                "access_token": self.access_token,
            }

            response = self.client.get(url, params=params)
            response.raise_for_status()
            user_data = response.json()

            return {
                "user_id": user_data.get("id"),
                "username": user_data.get("username"),
                "name": user_data.get("name"),
                "biography": user_data.get("threads_biography"),
                "profile_picture_url": user_data.get("threads_profile_picture_url"),
            }

        except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            logger.error("Threads API timeout during account info", error=str(e))
            raise ThreadsError(f"Timeout getting account info: {str(e)}")
        except Exception as e:
            logger.error("Failed to get Threads account info", error=str(e))
            raise ThreadsError(f"Failed to get account info: {str(e)}")

    def get_recent_threads(self, count: int = 5) -> List[Dict[str, any]]:
        """Get recent threads from the authenticated account."""
        try:
            url = f"{self.base_url}/v1.0/{self.user_id}/threads"
            params = {
                "fields": "id,media_type,media_url,permalink,username,text,timestamp,shortcode,thumbnail_url,children,is_quote_post",
                "limit": min(count, 25),  # Threads API limit
                "access_token": self.access_token,
            }

            response = self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if "data" not in data:
                return []

            recent_threads = []
            for thread in data["data"]:
                thread_info = {
                    "id": thread.get("id"),
                    "text": thread.get("text", ""),
                    "timestamp": thread.get("timestamp"),
                    "permalink": thread.get("permalink", ""),
                    "media_type": thread.get("media_type"),
                    "shortcode": thread.get("shortcode"),
                }

                recent_threads.append(thread_info)

            logger.info("Retrieved recent threads", count=len(recent_threads))
            return recent_threads

        except Exception as e:
            logger.error("Failed to get recent threads", error=str(e))
            raise ThreadsError(f"Failed to get recent threads: {str(e)}")

    def test_connection(self) -> bool:
        """Test Threads API connection and authentication."""
        try:
            account_info = self.get_account_info()
            if account_info and account_info.get("user_id"):
                logger.info(
                    "Threads connection test successful",
                    username=account_info.get("username"),
                )
                return True
            else:
                logger.error("Threads connection test failed - no user data")
                return False

        except Exception as e:
            logger.error("Threads connection test failed", error=str(e))
            return False

    def __del__(self):
        """Clean up HTTP client."""
        if hasattr(self, "client"):
            self.client.close()


# Convenience functions for use in other modules
async def post_thread_simple(thread_text: str, account_id: str = None) -> bool:
    """Simple thread posting function that returns success/failure."""
    try:
        poster = ThreadsPoster(account_id=account_id)
        result = await poster.post_thread(thread_text)
        return result["status"] in ["posted", "simulated"]
    except Exception as e:
        logger.error(
            "Simple thread posting failed", account_id=account_id, error=str(e)
        )
        return False


def test_threads_connection(account_id: str = None) -> bool:
    """Test Threads API connection."""
    try:
        poster = ThreadsPoster(account_id=account_id)
        return poster.test_connection()
    except Exception:
        return False


def get_threads_account_info(account_id: str = None) -> Optional[Dict[str, any]]:
    """Get Threads account information."""
    try:
        poster = ThreadsPoster(account_id=account_id)
        return poster.get_account_info()
    except Exception as e:
        logger.error(
            "Failed to get Threads account info", account_id=account_id, error=str(e)
        )
        return None
