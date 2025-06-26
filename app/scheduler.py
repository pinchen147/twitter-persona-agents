"""
Scheduling system for automated multi-account tweet posting with catch-up capabilities.

This module implements the core automation layer that ensures consistent tweet posting
across all configured accounts without manual intervention. It uses APScheduler for
reliable task scheduling and includes sophisticated catch-up logic for missed posts.

Key Features:
- Automated posting at configurable intervals (default: every 6 hours)
- Multi-account support with parallel posting
- Catch-up system for missed posting windows during downtime
- Health monitoring with automatic issue detection
- Graceful error handling and retry logic
- Emergency pause/resume capabilities

Architecture:
- Uses AsyncIOScheduler for non-blocking scheduled tasks
- Main posting job runs every N hours and posts to ALL accounts
- Catch-up detection runs on startup to handle missed windows
- Each account posts independently with isolated error handling
- Failed posts don't affect other accounts

Catch-up Logic:
- On startup, checks each account's last post time
- Calculates missed posting windows based on interval
- Schedules catch-up posts with 30-second spacing
- Limits catch-up posts to prevent timeline flooding
- Grace period prevents false positives during short downtimes

Configuration (config.yaml):
scheduler:
  enabled: true
  post_interval_hours: 6  # 4 posts per day
  catch_up_enabled: true
  max_catch_up_posts: 3
  catch_up_grace_period_hours: 1
"""

import asyncio
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.account_manager import get_account_ids
from app.deps import get_config
from app.exceptions import ZenKinkBotException
from app.generation import generate_and_post_tweet
from app.monitoring import ActivityLogger

logger = structlog.get_logger(__name__)


class TweetScheduler:
    """Manage automated tweet posting schedule."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.activity_logger = ActivityLogger()

        # Load configuration
        config = get_config()
        scheduler_config = config.get("scheduler", {})
        self.enabled = scheduler_config.get("enabled", True)
        self.interval_hours = scheduler_config.get(
            "post_interval_hours", 4
        )  # Changed from 6 to 4 hours (6 posts per day)
        self.timezone = scheduler_config.get("timezone", "UTC")

        # Catch-up configuration
        self.catch_up_enabled = scheduler_config.get("catch_up_enabled", True)
        self.max_catch_up_posts = scheduler_config.get("max_catch_up_posts", 2)
        self.catch_up_grace_period_hours = scheduler_config.get(
            "catch_up_grace_period_hours", 1
        )

        # Track state
        self.is_running = False
        self.next_run_time = None

    def start(self):
        """Start the scheduler."""
        if not self.enabled:
            logger.info("Scheduler disabled in configuration")
            return

        try:
            # Add the main posting job with fixed misfire handling
            self.scheduler.add_job(
                func=self._scheduled_post_job,
                trigger=IntervalTrigger(hours=self.interval_hours),
                id="main_posting_job",
                name="Automated Tweet Posting",
                misfire_grace_time=3600,  # 1 hour grace period
                max_instances=1,  # Only one instance at a time
                replace_existing=True,
                coalesce=True,  # Combine multiple missed runs into one
            )

            # Add a health check job every hour
            self.scheduler.add_job(
                func=self._health_check_job,
                trigger=IntervalTrigger(hours=1),
                id="health_check_job",
                name="Health Check",
                misfire_grace_time=3600,  # 1 hour grace period
                max_instances=1,
                replace_existing=True,
                coalesce=True,
            )

            # Start the scheduler
            self.scheduler.start()
            self.is_running = True

            # Force resume immediately after start to prevent APScheduler auto-pause
            if self.scheduler.running and self.scheduler.state == 1:  # STATE_PAUSED
                print(f"WARNING: Scheduler started in paused state, forcing resume...")
                self.scheduler.resume()
                # Double-check resume worked
                if self.scheduler.state == 1:
                    print(f"WARNING: Scheduler still paused after resume, retrying...")
                    # Clear any accumulated misfires and force resume again
                    for job in self.scheduler.get_jobs():
                        job.modify(
                            misfire_grace_time=None
                        )  # Remove misfire checking temporarily
                    self.scheduler.resume()

            # Update next run time
            self._update_next_run_time()

            # Check for missed posts and schedule catch-ups
            if self.catch_up_enabled:
                try:
                    catch_up_count = self.check_for_missed_posts()
                    if catch_up_count > 0:
                        logger.info(
                            "Startup catch-up check completed",
                            catch_up_posts_scheduled=catch_up_count,
                        )
                    else:
                        logger.info(
                            "Startup catch-up check completed - no missed posts"
                        )
                except Exception as e:
                    logger.error(
                        "Failed to check for missed posts on startup", error=str(e)
                    )

            logger.info(
                "Tweet scheduler started",
                interval_hours=self.interval_hours,
                timezone=self.timezone,
                next_run=self.next_run_time,
                catch_up_enabled=self.catch_up_enabled,
            )

            self.activity_logger.log_system_event(
                "scheduler_started",
                f"Automated posting started (every {self.interval_hours} hours) with catch-up: {self.catch_up_enabled}",
                level="INFO",
            )

        except Exception as e:
            logger.error("Failed to start scheduler", error=str(e))
            raise ZenKinkBotException(f"Scheduler startup failed: {str(e)}")

    def stop(self):
        """Stop the scheduler."""
        try:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=False)

            self.is_running = False
            self.next_run_time = None

            logger.info("Tweet scheduler stopped")
            self.activity_logger.log_system_event(
                "scheduler_stopped", "Automated posting stopped", level="INFO"
            )

        except Exception as e:
            logger.error("Error stopping scheduler", error=str(e))

    def pause(self):
        """Pause the scheduler temporarily."""
        try:
            if self.scheduler.running:
                self.scheduler.pause()

            logger.info("Tweet scheduler paused")
            self.activity_logger.log_system_event(
                "scheduler_paused", "Automated posting paused", level="WARNING"
            )

        except Exception as e:
            logger.error("Error pausing scheduler", error=str(e))

    def resume(self):
        """Resume the scheduler."""
        try:
            if self.scheduler.running:
                self.scheduler.resume()

            self._update_next_run_time()

            logger.info("Tweet scheduler resumed", next_run=self.next_run_time)
            self.activity_logger.log_system_event(
                "scheduler_resumed", "Automated posting resumed", level="INFO"
            )

        except Exception as e:
            logger.error("Error resuming scheduler", error=str(e))

    def get_status(self) -> dict:
        """Get current scheduler status."""
        status = {
            "enabled": self.enabled,
            "running": self.is_running,
            "paused": False,
            "interval_hours": self.interval_hours,
            "next_run_time": None,
            "jobs": [],
        }

        if self.scheduler.running:
            status["paused"] = self.scheduler.state == 1  # STATE_PAUSED = 1

            # Get job information
            for job in self.scheduler.get_jobs():
                job_info = {
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": str(job.next_run_time)
                    if job.next_run_time
                    else None,
                }
                status["jobs"].append(job_info)

                # Update next run time for main job
                if job.id == "main_posting_job" and job.next_run_time:
                    status["next_run_time"] = str(job.next_run_time)
                    self.next_run_time = job.next_run_time

        return status

    def schedule_immediate_post(self):
        """Schedule an immediate post (force post)."""
        try:
            # Schedule a one-time job to run immediately
            self.scheduler.add_job(
                func=self._scheduled_post_job,
                trigger="date",  # Run once at specified time
                run_date=datetime.now() + timedelta(seconds=5),  # 5 seconds from now
                id="immediate_post",
                name="Immediate Tweet Post",
                misfire_grace_time=30,
                max_instances=1,
                replace_existing=True,
            )

            logger.info("Immediate post scheduled")

        except Exception as e:
            logger.error("Failed to schedule immediate post", error=str(e))
            raise ZenKinkBotException(f"Failed to schedule immediate post: {str(e)}")

    async def _scheduled_post_job(self):
        """The main scheduled posting job - posts one tweet per account."""
        try:
            logger.info("Starting scheduled multi-account tweet generation and posting")

            # Check if emergency stop is active
            from app.main import emergency_stop

            if emergency_stop:
                logger.warning("Scheduled post skipped due to emergency stop")
                self.activity_logger.log_system_event(
                    "scheduled_post_skipped",
                    "Scheduled post skipped - emergency stop active",
                    level="WARNING",
                )
                return

            # Get all available accounts
            account_ids = get_account_ids()
            if not account_ids:
                logger.warning("No accounts found, skipping scheduled post")
                self.activity_logger.log_system_event(
                    "scheduled_post_skipped", "No accounts configured", level="WARNING"
                )
                return

            logger.info(
                "Posting to accounts",
                account_count=len(account_ids),
                accounts=account_ids,
            )

            # Post one tweet per account
            all_results = []
            successful_posts = 0
            failed_posts = 0

            for account_id in account_ids:
                try:
                    logger.info("Posting for account", account_id=account_id)
                    result = await generate_and_post_tweet(account_id=account_id)
                    result["account_id"] = account_id
                    all_results.append(result)

                    if result["status"] == "success":
                        successful_posts += 1
                        logger.info(
                            "Scheduled tweet posted successfully for account",
                            account_id=account_id,
                            tweet_id=result.get("twitter_id"),
                            character_count=result.get("character_count"),
                        )
                    else:
                        failed_posts += 1
                        logger.error(
                            "Scheduled tweet posting failed for account",
                            account_id=account_id,
                            error=result.get("error"),
                        )

                except Exception as e:
                    failed_posts += 1
                    logger.error(
                        "Scheduled post failed for account",
                        account_id=account_id,
                        error=str(e),
                    )
                    all_results.append(
                        {"account_id": account_id, "status": "failed", "error": str(e)}
                    )

            # Log overall results
            logger.info(
                "Scheduled posting complete",
                total_accounts=len(account_ids),
                successful=successful_posts,
                failed=failed_posts,
            )

            self.activity_logger.log_system_event(
                "scheduled_multi_post_complete",
                f"Multi-account scheduled posting: {successful_posts} success, {failed_posts} failed",
                level="INFO" if failed_posts == 0 else "WARNING",
                metadata={
                    "total_accounts": len(account_ids),
                    "successful": successful_posts,
                    "failed": failed_posts,
                    "results": all_results,
                },
            )

        except Exception as e:
            logger.error("Scheduled post job failed", error=str(e))

            self.activity_logger.log_system_event(
                "scheduled_post_error",
                f"Scheduled post job error: {str(e)}",
                level="ERROR",
            )

    async def _health_check_job(self):
        """Periodic health check job."""
        try:
            logger.debug("Running scheduled health check")

            # Basic health checks
            from app.security import check_emergency_status

            emergency_conditions = check_emergency_status()

            if emergency_conditions:
                logger.warning("Health check found issues", issues=emergency_conditions)

                self.activity_logger.log_system_event(
                    "health_check_warning",
                    f"Health issues detected: {', '.join(emergency_conditions)}",
                    level="WARNING",
                    metadata={"issues": emergency_conditions},
                )

                # If critical issues, consider pausing
                critical_keywords = ["cost limit", "error rate", "failed"]
                if any(
                    keyword in condition.lower()
                    for condition in emergency_conditions
                    for keyword in critical_keywords
                ):
                    logger.warning("Critical health issues detected, considering pause")
            else:
                logger.debug("Health check passed")

        except Exception as e:
            logger.error("Health check job failed", error=str(e))

    def _update_next_run_time(self):
        """Update the next run time from scheduler."""
        try:
            if self.scheduler.running:
                job = self.scheduler.get_job("main_posting_job")
                if job and job.next_run_time:
                    self.next_run_time = job.next_run_time
        except Exception as e:
            logger.error("Failed to update next run time", error=str(e))

    def check_for_missed_posts(self) -> int:
        """
        Check for missed posting opportunities and schedule catch-up posts.
        Returns the number of catch-up posts scheduled.
        """
        if not self.catch_up_enabled:
            logger.info("Catch-up posting disabled")
            return 0

        try:
            # Get all available accounts
            account_ids = get_account_ids()
            if not account_ids:
                logger.info("No accounts found for missed posts check")
                return 0

            scheduled_catch_ups = 0
            current_time = datetime.now()

            for account_id in account_ids:
                try:
                    # Get last successful post time for this account
                    last_post_time = self.activity_logger.get_account_last_post_time(
                        account_id
                    )

                    if last_post_time is None:
                        # No previous posts for this account, schedule one catch-up
                        logger.info(
                            "No previous posts found for account, scheduling catch-up",
                            account_id=account_id,
                        )
                        self._schedule_catch_up_post(
                            account_id, delay_seconds=scheduled_catch_ups * 30
                        )
                        scheduled_catch_ups += 1
                        continue

                    # Calculate time since last post
                    time_since_last_post = current_time - last_post_time
                    hours_since_last_post = time_since_last_post.total_seconds() / 3600

                    # Calculate how many posting intervals have passed
                    expected_posts = int(
                        (hours_since_last_post - self.catch_up_grace_period_hours)
                        / self.interval_hours
                    )

                    if expected_posts > 0:
                        # Limit catch-up posts to avoid spam
                        catch_up_posts_needed = min(
                            expected_posts, self.max_catch_up_posts
                        )

                        logger.info(
                            "Missed posts detected for account",
                            account_id=account_id,
                            hours_since_last_post=round(hours_since_last_post, 2),
                            expected_posts=expected_posts,
                            catch_up_posts_needed=catch_up_posts_needed,
                        )

                        # Schedule catch-up posts with staggered timing
                        for i in range(catch_up_posts_needed):
                            delay_seconds = (
                                scheduled_catch_ups * 120
                            )  # 2 minutes between catch-up posts to avoid rate limits
                            self._schedule_catch_up_post(account_id, delay_seconds)
                            scheduled_catch_ups += 1

                            # Stop if we've reached the global limit
                            if scheduled_catch_ups >= self.max_catch_up_posts * len(
                                account_ids
                            ):
                                break
                    else:
                        logger.debug(
                            "No missed posts for account",
                            account_id=account_id,
                            hours_since_last_post=round(hours_since_last_post, 2),
                        )

                except Exception as e:
                    logger.error(
                        "Error checking missed posts for account",
                        account_id=account_id,
                        error=str(e),
                    )

            if scheduled_catch_ups > 0:
                logger.info("Scheduled catch-up posts", count=scheduled_catch_ups)
                self.activity_logger.log_system_event(
                    "catch_up_posts_scheduled",
                    f"Scheduled {scheduled_catch_ups} catch-up posts due to missed posting windows",
                    level="INFO",
                    metadata={
                        "catch_up_count": scheduled_catch_ups,
                        "accounts": account_ids,
                    },
                )
            else:
                logger.info("No catch-up posts needed")

            return scheduled_catch_ups

        except Exception as e:
            logger.error("Failed to check for missed posts", error=str(e))
            return 0

    def _schedule_catch_up_post(self, account_id: str, delay_seconds: int = 0):
        """Schedule a single catch-up post for an account."""
        try:
            # Use more precise timestamp to avoid conflicts
            timestamp = time.time()
            unique_id = str(uuid.uuid4())[:8]  # Short unique identifier
            job_id = f"catch_up_post_{account_id}_{timestamp:.3f}_{unique_id}"
            run_time = datetime.now() + timedelta(seconds=max(60, delay_seconds))

            self.scheduler.add_job(
                func=self._catch_up_post_job,
                args=[account_id],
                trigger="date",
                run_date=run_time,
                id=job_id,
                name=f"Catch-up Tweet Post for {account_id}",
                misfire_grace_time=60,
                max_instances=1,
                replace_existing=True,  # Allow replacing existing jobs
            )

            logger.info(
                "Catch-up post scheduled",
                account_id=account_id,
                run_time=run_time,
                job_id=job_id,
            )

        except Exception as e:
            logger.error(
                "Failed to schedule catch-up post", account_id=account_id, error=str(e)
            )
            # If it's a job conflict, try with a different ID
            if "conflicts with an existing job" in str(e):
                logger.info("Job conflict detected, retrying with different ID", account_id=account_id)
                # Retry with a new unique ID
                timestamp = time.time()
                unique_id = str(uuid.uuid4())[:8]
                backup_job_id = f"catch_up_retry_{account_id}_{timestamp:.3f}_{unique_id}"
                try:
                    self.scheduler.add_job(
                        func=self._catch_up_post_job,
                        args=[account_id],
                        trigger="date",
                        run_date=run_time,
                        id=backup_job_id,
                        name=f"Catch-up Tweet Post for {account_id} (retry)",
                        misfire_grace_time=60,
                        max_instances=1,
                        replace_existing=True,
                    )
                    logger.info("Retry job scheduled successfully", account_id=account_id, job_id=backup_job_id)
                except Exception as retry_e:
                    logger.error("Retry job scheduling also failed", account_id=account_id, error=str(retry_e))

    async def _catch_up_post_job(self, account_id: str):
        """Execute a catch-up post for a specific account."""
        try:
            logger.info("Executing catch-up post", account_id=account_id)

            # Check if emergency stop is active
            from app.main import emergency_stop

            if emergency_stop:
                logger.warning(
                    "Catch-up post skipped due to emergency stop", account_id=account_id
                )
                return

            # Generate and post tweet
            result = await generate_and_post_tweet(account_id=account_id)

            if result["status"] == "success":
                logger.info(
                    "Catch-up tweet posted successfully",
                    account_id=account_id,
                    tweet_id=result.get("twitter_id"),
                    character_count=result.get("character_count"),
                )

                self.activity_logger.log_system_event(
                    "catch_up_post_success",
                    f"Catch-up tweet posted successfully for {account_id}",
                    level="INFO",
                    metadata={"account_id": account_id, "result": result},
                )
            else:
                logger.error(
                    "Catch-up tweet posting failed",
                    account_id=account_id,
                    error=result.get("error"),
                )

                self.activity_logger.log_system_event(
                    "catch_up_post_failed",
                    f"Catch-up tweet posting failed for {account_id}: {result.get('error')}",
                    level="ERROR",
                    metadata={"account_id": account_id, "result": result},
                )

        except Exception as e:
            logger.error(
                "Catch-up post job failed", account_id=account_id, error=str(e)
            )
            self.activity_logger.log_system_event(
                "catch_up_post_error",
                f"Catch-up post job error for {account_id}: {str(e)}",
                level="ERROR",
                metadata={"account_id": account_id, "error": str(e)},
            )


# Global scheduler instance
_scheduler_instance: Optional[TweetScheduler] = None


def get_scheduler() -> TweetScheduler:
    """Get the global scheduler instance."""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = TweetScheduler()
    return _scheduler_instance


def start_scheduler():
    """Start the global scheduler."""
    scheduler = get_scheduler()
    scheduler.start()


def stop_scheduler():
    """Stop the global scheduler."""
    global _scheduler_instance
    if _scheduler_instance:
        _scheduler_instance.stop()
        _scheduler_instance = None


def get_scheduler_status() -> dict:
    """Get scheduler status."""
    try:
        scheduler = get_scheduler()
        return scheduler.get_status()
    except Exception as e:
        logger.error("Failed to get scheduler status", error=str(e))
        return {"enabled": False, "running": False, "error": str(e)}


async def force_immediate_post():
    """Force an immediate post outside of schedule."""
    try:
        scheduler = get_scheduler()
        scheduler.schedule_immediate_post()
        return True
    except Exception as e:
        logger.error("Failed to force immediate post", error=str(e))
        return False
