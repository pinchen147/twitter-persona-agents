"""
Multi-platform poster - Unified posting to Twitter and Threads.

This module provides a unified interface for posting content to multiple social media platforms
simultaneously. It handles platform-specific adaptations, error handling, and success tracking
across all configured platforms.

Key Features:
- Unified posting interface for Twitter and Threads
- Platform-specific content adaptation
- Comprehensive error handling with partial success tracking
- Rate limiting coordination across platforms
- Detailed logging and monitoring for each platform
- Account-specific platform configuration

Architecture:
- Uses existing Twitter and Threads clients
- Coordinates posting across all enabled platforms
- Handles platform-specific failures gracefully
- Provides detailed success/failure reporting
- Integrates with existing monitoring systems

The module ensures reliable multi-platform posting with proper error handling,
rate limit compliance, and comprehensive logging for debugging.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

import structlog

from app.exceptions import ZenKinkBotException
from app.monitoring import ActivityLogger
from app.threads_client import ThreadsPoster
from app.twitter_client import TwitterPoster

logger = structlog.get_logger(__name__)


class MultiPlatformError(ZenKinkBotException):
    """Custom exception for multi-platform posting errors."""

    pass


class MultiPlatformPoster:
    """Handle posting to multiple social media platforms simultaneously."""

    def __init__(self, account_id: str = None):
        self.account_id = account_id
        self.activity_logger = ActivityLogger()

        if not account_id:
            raise MultiPlatformError(
                "Account ID is required for multi-platform posting"
            )

        # Load account configuration to determine enabled platforms
        from app.account_manager import get_account

        self.account = get_account(account_id)
        if not self.account:
            raise MultiPlatformError(f"Account {account_id} not found")

        # Get enabled platforms (default to Twitter only for backward compatibility)
        self.enabled_platforms = self.account.get("posting_platforms", ["twitter"])

        # Initialize platform-specific posters
        self.posters = {}
        self.platform_configs = {}

        # Initialize Twitter poster if enabled
        if "twitter" in self.enabled_platforms:
            try:
                self.posters["twitter"] = TwitterPoster(account_id=account_id)
                self.platform_configs["twitter"] = {
                    "character_limit": 280,
                    "platform_name": "Twitter",
                }
                logger.info("Twitter poster initialized", account_id=account_id)
            except Exception as e:
                logger.warning(
                    "Failed to initialize Twitter poster",
                    account_id=account_id,
                    error=str(e),
                )

        # Initialize Threads poster if enabled
        if "threads" in self.enabled_platforms:
            try:
                self.posters["threads"] = ThreadsPoster(account_id=account_id)
                self.platform_configs["threads"] = {
                    "character_limit": 500,
                    "platform_name": "Threads",
                }
                logger.info("Threads poster initialized", account_id=account_id)
            except Exception as e:
                logger.warning(
                    "Failed to initialize Threads poster",
                    account_id=account_id,
                    error=str(e),
                )

        if not self.posters:
            raise MultiPlatformError(
                f"No platforms could be initialized for account {account_id}"
            )

    def adapt_content_for_platform(self, content: str, platform: str) -> str:
        """Adapt content for specific platform requirements."""
        platform_config = self.platform_configs.get(platform, {})
        character_limit = platform_config.get("character_limit", 280)

        # If content is too long for this platform, truncate it
        if len(content) > character_limit:
            truncated = content[: character_limit - 3] + "..."
            logger.info(
                "Content truncated for platform",
                platform=platform,
                original_length=len(content),
                truncated_length=len(truncated),
            )
            return truncated

        return content

    async def post_to_platform(self, platform: str, content: str) -> Dict[str, Any]:
        """Post content to a specific platform."""
        if platform not in self.posters:
            return {
                "platform": platform,
                "status": "failed",
                "error": f"Platform {platform} not initialized",
            }

        try:
            poster = self.posters[platform]
            adapted_content = self.adapt_content_for_platform(content, platform)

            logger.info(
                "Posting to platform",
                platform=platform,
                content_length=len(adapted_content),
            )

            if platform == "twitter":
                result = await poster.post_tweet(adapted_content)
                return {
                    "platform": platform,
                    "status": result.get("status", "unknown"),
                    "post_id": result.get("twitter_id"),
                    "url": result.get("url"),
                    "message": result.get("message"),
                    "posted_at": result.get("posted_at"),
                    "api_time_ms": result.get("api_time_ms"),
                }
            elif platform == "threads":
                result = await poster.post_thread(adapted_content)
                return {
                    "platform": platform,
                    "status": result.get("status", "unknown"),
                    "post_id": result.get("threads_id"),
                    "url": result.get("url"),
                    "message": result.get("message"),
                    "posted_at": result.get("posted_at"),
                    "api_time_ms": result.get("api_time_ms"),
                }
            else:
                return {
                    "platform": platform,
                    "status": "failed",
                    "error": f"Unknown platform: {platform}",
                }

        except Exception as e:
            logger.error("Failed to post to platform", platform=platform, error=str(e))
            return {"platform": platform, "status": "failed", "error": str(e)}

    async def post_to_all_platforms(self, content: str) -> Dict[str, Any]:
        """Post content to all enabled platforms simultaneously."""
        logger.info(
            "Starting multi-platform post",
            account_id=self.account_id,
            platforms=list(self.posters.keys()),
            content_length=len(content),
        )

        start_time = time.time()

        # Post to all platforms simultaneously
        platform_tasks = []
        for platform in self.posters.keys():
            task = self.post_to_platform(platform, content)
            platform_tasks.append(task)

        # Wait for all posts to complete
        platform_results = await asyncio.gather(*platform_tasks, return_exceptions=True)

        # Process results
        results = []
        successful_platforms = []
        failed_platforms = []

        for i, result in enumerate(platform_results):
            platform = list(self.posters.keys())[i]

            if isinstance(result, Exception):
                error_result = {
                    "platform": platform,
                    "status": "failed",
                    "error": str(result),
                }
                results.append(error_result)
                failed_platforms.append(platform)
                logger.error(
                    "Platform post failed with exception",
                    platform=platform,
                    error=str(result),
                )
            else:
                results.append(result)
                if result.get("status") in ["posted", "simulated"]:
                    successful_platforms.append(platform)
                else:
                    failed_platforms.append(platform)

        total_time = int((time.time() - start_time) * 1000)

        # Determine overall status
        if successful_platforms and not failed_platforms:
            overall_status = "success"
        elif successful_platforms and failed_platforms:
            overall_status = "partial_success"
        else:
            overall_status = "failed"

        # Log activity for each platform
        for result in results:
            platform = result["platform"]
            platform_name = self.platform_configs.get(platform, {}).get(
                "platform_name", platform
            )

            self.activity_logger.log_system_event(
                event_type=f"{platform}_post",
                message=f"Posted to {platform_name} for account {self.account_id}: {result.get('status', 'unknown')}",
                level="INFO"
                if result.get("status") in ["posted", "simulated"]
                else "ERROR",
                metadata={
                    "account_id": self.account_id,
                    "platform": platform,
                    "status": result.get("status"),
                    "post_id": result.get("post_id"),
                    "error": result.get("error"),
                    "api_time_ms": result.get("api_time_ms"),
                    "content_length": len(content),
                },
            )

        summary = {
            "status": overall_status,
            "account_id": self.account_id,
            "content": content,
            "character_count": len(content),
            "total_time_ms": total_time,
            "platforms": {
                "attempted": list(self.posters.keys()),
                "successful": successful_platforms,
                "failed": failed_platforms,
            },
            "results": results,
        }

        logger.info(
            "Multi-platform post complete",
            overall_status=overall_status,
            successful_platforms=successful_platforms,
            failed_platforms=failed_platforms,
            total_time_ms=total_time,
        )

        return summary

    def get_platform_info(self) -> Dict[str, Any]:
        """Get information about configured platforms."""
        platform_info = {}

        for platform, poster in self.posters.items():
            try:
                if platform == "twitter":
                    info = poster.get_account_info()
                    platform_info[platform] = {
                        "platform_name": "Twitter",
                        "status": "connected",
                        "account_info": info,
                    }
                elif platform == "threads":
                    info = poster.get_account_info()
                    platform_info[platform] = {
                        "platform_name": "Threads",
                        "status": "connected",
                        "account_info": info,
                    }
            except Exception as e:
                platform_info[platform] = {
                    "platform_name": self.platform_configs.get(platform, {}).get(
                        "platform_name", platform
                    ),
                    "status": "error",
                    "error": str(e),
                }

        return {
            "account_id": self.account_id,
            "enabled_platforms": self.enabled_platforms,
            "platforms": platform_info,
        }

    def test_all_connections(self) -> Dict[str, Any]:
        """Test connections to all configured platforms."""
        connection_results = {}

        for platform, poster in self.posters.items():
            try:
                if platform == "twitter":
                    success = poster.test_connection()
                elif platform == "threads":
                    success = poster.test_connection()
                else:
                    success = False

                connection_results[platform] = {
                    "platform_name": self.platform_configs.get(platform, {}).get(
                        "platform_name", platform
                    ),
                    "status": "connected" if success else "failed",
                    "tested_at": time.time(),
                }
            except Exception as e:
                connection_results[platform] = {
                    "platform_name": self.platform_configs.get(platform, {}).get(
                        "platform_name", platform
                    ),
                    "status": "error",
                    "error": str(e),
                    "tested_at": time.time(),
                }

        return {"account_id": self.account_id, "connections": connection_results}


# Convenience functions for use in other modules
async def post_to_all_platforms(content: str, account_id: str = None) -> Dict[str, Any]:
    """Simple multi-platform posting function."""
    try:
        poster = MultiPlatformPoster(account_id=account_id)
        return await poster.post_to_all_platforms(content)
    except Exception as e:
        logger.error(
            "Multi-platform posting failed", account_id=account_id, error=str(e)
        )
        return {"status": "failed", "error": str(e), "account_id": account_id}


def test_all_platform_connections(account_id: str = None) -> Dict[str, Any]:
    """Test connections to all platforms for an account."""
    try:
        poster = MultiPlatformPoster(account_id=account_id)
        return poster.test_all_connections()
    except Exception as e:
        logger.error("Connection test failed", account_id=account_id, error=str(e))
        return {"account_id": account_id, "status": "error", "error": str(e)}


def get_platform_info(account_id: str = None) -> Dict[str, Any]:
    """Get platform information for an account."""
    try:
        poster = MultiPlatformPoster(account_id=account_id)
        return poster.get_platform_info()
    except Exception as e:
        logger.error("Failed to get platform info", account_id=account_id, error=str(e))
        return {"account_id": account_id, "status": "error", "error": str(e)}
