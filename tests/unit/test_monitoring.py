"""Unit tests for monitoring functionality."""

import pytest
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import os

from app.monitoring import CostTracker, ActivityLogger, HealthChecker


class TestCostTracker:
    """Test CostTracker functionality."""
    
    @pytest.fixture
    def temp_cost_tracker(self):
        """Create a temporary cost tracker for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create temporary database
            temp_db = Path(temp_dir) / "test_cost.db"
            
            # Mock the db_path
            original_init = CostTracker.__init__
            
            def mock_init(self, daily_limit=10.0):
                self.daily_limit = daily_limit
                self.db_path = temp_db
                self._init_db()
            
            CostTracker.__init__ = mock_init
            
            tracker = CostTracker(daily_limit=5.0)
            
            yield tracker
            
            # Restore original init
            CostTracker.__init__ = original_init
    
    def test_record_cost(self, temp_cost_tracker):
        """Test recording API costs."""
        temp_cost_tracker.record_cost("openai", "completion", 2.50, tokens_used=1000)
        
        daily_cost = temp_cost_tracker.get_daily_cost()
        assert daily_cost == 2.50
    
    def test_daily_limit_check(self, temp_cost_tracker):
        """Test daily limit checking."""
        # Should be within limit initially
        assert temp_cost_tracker.check_daily_limit() is True
        
        # Add cost that exceeds limit
        temp_cost_tracker.record_cost("openai", "completion", 6.0)
        
        # Should now exceed limit
        assert temp_cost_tracker.check_daily_limit() is False
    
    def test_cost_breakdown(self, temp_cost_tracker):
        """Test cost breakdown by service."""
        temp_cost_tracker.record_cost("openai", "completion", 2.0)
        temp_cost_tracker.record_cost("openai", "embedding", 0.50)
        temp_cost_tracker.record_cost("twitter", "post", 0.01)
        
        breakdown = temp_cost_tracker.get_cost_breakdown(days=1)
        
        assert breakdown["openai"] == 2.50
        assert breakdown["twitter"] == 0.01


class TestActivityLogger:
    """Test ActivityLogger functionality."""
    
    @pytest.fixture
    def temp_activity_logger(self):
        """Create a temporary activity logger for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create temporary database
            temp_db = Path(temp_dir) / "test_activity.db"
            
            # Mock the db_path
            original_init = ActivityLogger.__init__
            
            def mock_init(self):
                self.db_path = temp_db
                self._init_db()
            
            ActivityLogger.__init__ = mock_init
            
            logger = ActivityLogger()
            
            yield logger
            
            # Restore original init
            ActivityLogger.__init__ = original_init
    
    def test_log_post_attempt(self, temp_activity_logger):
        """Test logging post attempts."""
        temp_activity_logger.log_post_attempt(
            tweet_text="Test tweet",
            seed_chunk_hash="abc123",
            status="success",
            twitter_id="123456789"
        )
        
        recent_posts = temp_activity_logger.get_recent_posts(limit=1)
        assert len(recent_posts) == 1
        assert recent_posts[0]["tweet_text"] == "Test tweet"
        assert recent_posts[0]["status"] == "success"
    
    def test_log_system_event(self, temp_activity_logger):
        """Test logging system events."""
        temp_activity_logger.log_system_event(
            event_type="startup",
            message="System started",
            level="INFO"
        )
        
        # Verify event was logged (would need to add getter method in real implementation)
        with sqlite3.connect(temp_activity_logger.db_path) as conn:
            cursor = conn.execute("SELECT * FROM system_events")
            events = cursor.fetchall()
            assert len(events) == 1
    
    def test_deduplication_tracking(self, temp_activity_logger):
        """Test recent seed hash tracking for deduplication."""
        # Log some posts with different hashes
        temp_activity_logger.log_post_attempt("Tweet 1", "hash1", "success")
        temp_activity_logger.log_post_attempt("Tweet 2", "hash2", "success")
        temp_activity_logger.log_post_attempt("Tweet 3", "hash3", "success")
        
        recent_hashes = temp_activity_logger.get_recent_seed_hashes(limit=2)
        assert len(recent_hashes) == 2
        assert "hash3" in recent_hashes  # Most recent
        assert "hash2" in recent_hashes
    
    def test_success_rate_calculation(self, temp_activity_logger):
        """Test success rate calculation."""
        # Add some successful and failed posts
        temp_activity_logger.log_post_attempt("Success 1", "hash1", "success")
        temp_activity_logger.log_post_attempt("Success 2", "hash2", "success")
        temp_activity_logger.log_post_attempt("Failed 1", "hash3", "failed")
        
        success_rate = temp_activity_logger.get_success_rate(hours=24)
        assert success_rate == 2/3  # 2 successes out of 3 total


@pytest.mark.unit
class TestHealthChecker:
    """Test HealthChecker functionality."""
    
    @pytest.fixture
    def mock_health_checker(self):
        """Create a health checker with mocked dependencies."""
        
        # Create mock cost tracker
        cost_tracker = CostTracker(daily_limit=10.0)
        
        # Create mock activity logger
        activity_logger = ActivityLogger()
        
        # Create health checker
        health_checker = HealthChecker(cost_tracker, activity_logger)
        
        return health_checker
    
    def test_health_check_structure(self, mock_health_checker):
        """Test that health check returns proper structure."""
        # Mock the check methods to avoid file system dependencies
        mock_health_checker._check_config = lambda: {"healthy": True, "message": "OK"}
        mock_health_checker._check_files = lambda: {"healthy": True, "message": "OK"}
        mock_health_checker._check_cost_limits = lambda: {"healthy": True, "message": "OK"}
        
        health_status = mock_health_checker.check_health(deep=False)
        
        assert "timestamp" in health_status
        assert "status" in health_status
        assert "checks" in health_status
        assert "config" in health_status["checks"]
        assert "files" in health_status["checks"]
        assert "cost_limits" in health_status["checks"]
    
    def test_health_check_failure_detection(self, mock_health_checker):
        """Test that failed checks are properly detected."""
        # Mock some failures
        mock_health_checker._check_config = lambda: {"healthy": False, "message": "Config error"}
        mock_health_checker._check_files = lambda: {"healthy": True, "message": "OK"}
        mock_health_checker._check_cost_limits = lambda: {"healthy": True, "message": "OK"}
        
        health_status = mock_health_checker.check_health(deep=False)
        
        assert health_status["status"] == "unhealthy"
        assert "failed_checks" in health_status
        assert "config" in health_status["failed_checks"]