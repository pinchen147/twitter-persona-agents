"""Scheduling system for automated tweet posting."""

import asyncio
from datetime import datetime, timedelta
from typing import Optional
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from app.deps import get_config
from app.generation import generate_and_post_tweet
from app.monitoring import ActivityLogger
from app.exceptions import ZenKinkBotException

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
        self.interval_hours = scheduler_config.get("post_interval_hours", 8)
        self.timezone = scheduler_config.get("timezone", "UTC")
        
        # Track state
        self.is_running = False
        self.next_run_time = None
        
    def start(self):
        """Start the scheduler."""
        if not self.enabled:
            logger.info("Scheduler disabled in configuration")
            return
        
        try:
            # Add the main posting job
            self.scheduler.add_job(
                func=self._scheduled_post_job,
                trigger=IntervalTrigger(hours=self.interval_hours),
                id="main_posting_job",
                name="Automated Tweet Posting",
                misfire_grace_time=300,  # 5 minutes grace period
                max_instances=1,  # Only one instance at a time
                replace_existing=True
            )
            
            # Add a health check job every hour
            self.scheduler.add_job(
                func=self._health_check_job,
                trigger=IntervalTrigger(hours=1),
                id="health_check_job",
                name="Health Check",
                misfire_grace_time=600,  # 10 minutes grace period
                max_instances=1,
                replace_existing=True
            )
            
            # Start the scheduler
            self.scheduler.start()
            self.is_running = True
            
            # Update next run time
            self._update_next_run_time()
            
            logger.info("Tweet scheduler started", 
                       interval_hours=self.interval_hours,
                       timezone=self.timezone,
                       next_run=self.next_run_time)
            
            self.activity_logger.log_system_event(
                "scheduler_started",
                f"Automated posting started (every {self.interval_hours} hours)",
                level="INFO"
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
                "scheduler_stopped",
                "Automated posting stopped",
                level="INFO"
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
                "scheduler_paused",
                "Automated posting paused",
                level="WARNING"
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
                "scheduler_resumed",
                "Automated posting resumed",
                level="INFO"
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
            "jobs": []
        }
        
        if self.scheduler.running:
            status["paused"] = self.scheduler.state == 1  # STATE_PAUSED = 1
            
            # Get job information
            for job in self.scheduler.get_jobs():
                job_info = {
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": str(job.next_run_time) if job.next_run_time else None
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
                trigger='date',  # Run once at specified time
                run_date=datetime.now() + timedelta(seconds=5),  # 5 seconds from now
                id="immediate_post",
                name="Immediate Tweet Post",
                misfire_grace_time=30,
                max_instances=1,
                replace_existing=True
            )
            
            logger.info("Immediate post scheduled")
            
        except Exception as e:
            logger.error("Failed to schedule immediate post", error=str(e))
            raise ZenKinkBotException(f"Failed to schedule immediate post: {str(e)}")
    
    async def _scheduled_post_job(self):
        """The main scheduled posting job."""
        try:
            logger.info("Starting scheduled tweet generation and posting")
            
            # Check if emergency stop is active
            from app.main import emergency_stop
            if emergency_stop:
                logger.warning("Scheduled post skipped due to emergency stop")
                self.activity_logger.log_system_event(
                    "scheduled_post_skipped",
                    "Scheduled post skipped - emergency stop active",
                    level="WARNING"
                )
                return
            
            # Generate and post tweet
            result = await generate_and_post_tweet()
            
            if result["status"] == "success":
                logger.info("Scheduled tweet posted successfully", 
                           tweet_id=result.get("twitter_id"),
                           character_count=result.get("character_count"))
                
                self.activity_logger.log_system_event(
                    "scheduled_post_success",
                    f"Scheduled tweet posted: {result.get('twitter_id', 'unknown')}",
                    level="INFO",
                    metadata=result
                )
            else:
                logger.error("Scheduled tweet posting failed", 
                           error=result.get("error"))
                
                self.activity_logger.log_system_event(
                    "scheduled_post_failed",
                    f"Scheduled post failed: {result.get('error', 'unknown error')}",
                    level="ERROR",
                    metadata=result
                )
            
        except Exception as e:
            logger.error("Scheduled post job failed", error=str(e))
            
            self.activity_logger.log_system_event(
                "scheduled_post_error",
                f"Scheduled post job error: {str(e)}",
                level="ERROR"
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
                    metadata={"issues": emergency_conditions}
                )
                
                # If critical issues, consider pausing
                critical_keywords = ["cost limit", "error rate", "failed"]
                if any(keyword in condition.lower() for condition in emergency_conditions for keyword in critical_keywords):
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
        return {
            "enabled": False,
            "running": False,
            "error": str(e)
        }


async def force_immediate_post():
    """Force an immediate post outside of schedule."""
    try:
        scheduler = get_scheduler()
        scheduler.schedule_immediate_post()
        return True
    except Exception as e:
        logger.error("Failed to force immediate post", error=str(e))
        return False