"""
Monitoring and observability system - Comprehensive tracking and health management.

This module provides the core monitoring infrastructure for the bot system, tracking
costs, activity, performance metrics, and system health. It uses SQLite for 
persistent storage and provides real-time metrics for the dashboard.

Key Components:
1. CostTracker: Monitors API usage costs with daily limits and emergency stops
2. ActivityLogger: Records all tweet attempts, system events, and errors
3. HealthChecker: Validates system components and external dependencies

Features:
- Real-time cost tracking with configurable daily limits
- Comprehensive activity logging with SQLite persistence
- Success rate calculations and performance metrics
- Emergency stop triggers based on cost/error thresholds
- Account-specific tracking for multi-account support
- Automated database backups and rotation

Database Schema:
- post_attempts: Tweet generation/posting history
- system_events: Important system activities
- api_costs: Detailed cost breakdown by service

The monitoring system enables operators to:
- Track spending and prevent cost overruns
- Analyze posting patterns and success rates
- Debug issues with detailed logs
- Monitor system health proactively
- Generate reports for optimization
"""

import json
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import structlog

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class CostTracker:
    """Track API costs and enforce limits."""
    
    def __init__(self, daily_limit: float = 10.0):
        self.daily_limit = daily_limit
        self.db_path = Path("data/cost_tracking.db")
        self._init_db()
    
    def _init_db(self):
        """Initialize cost tracking database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_costs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    service TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    cost_usd REAL NOT NULL,
                    tokens_used INTEGER,
                    metadata TEXT
                )
            """)
            conn.commit()
    
    def record_cost(self, service: str, operation: str, cost_usd: float, 
                   tokens_used: Optional[int] = None, metadata: Optional[dict] = None):
        """Record an API cost."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO api_costs (service, operation, cost_usd, tokens_used, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, (service, operation, cost_usd, tokens_used, json.dumps(metadata) if metadata else None))
            conn.commit()
        
        logger.info("API cost recorded", 
                   service=service, operation=operation, cost_usd=cost_usd, tokens_used=tokens_used)
    
    def get_daily_cost(self, date: Optional[datetime] = None) -> float:
        """Get total cost for a specific day."""
        if date is None:
            date = datetime.now()
        
        start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT COALESCE(SUM(cost_usd), 0) 
                FROM api_costs 
                WHERE timestamp >= ? AND timestamp < ?
            """, (start_of_day, end_of_day))
            return cursor.fetchone()[0]
    
    def check_daily_limit(self) -> bool:
        """Check if daily cost limit has been exceeded."""
        daily_cost = self.get_daily_cost()
        return daily_cost < self.daily_limit
    
    def get_cost_breakdown(self, days: int = 7) -> Dict[str, float]:
        """Get cost breakdown by service for the last N days."""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT service, SUM(cost_usd) 
                FROM api_costs 
                WHERE timestamp >= ?
                GROUP BY service
            """, (cutoff_date,))
            return dict(cursor.fetchall())


class ActivityLogger:
    """Log bot activities and posting history."""
    
    def __init__(self):
        self.db_path = Path("data/post_history.db")
        self._init_db()
    
    def _init_db(self):
        """Initialize activity logging database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS post_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    account_id TEXT,
                    tweet_text TEXT NOT NULL,
                    seed_chunk_hash TEXT,
                    status TEXT NOT NULL,
                    twitter_id TEXT,
                    error_message TEXT,
                    generation_time_ms INTEGER,
                    metadata TEXT
                )
            """)
            
            # Add account_id column if it doesn't exist (for existing databases)
            try:
                conn.execute("ALTER TABLE post_history ADD COLUMN account_id TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                # Column already exists
                pass
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS system_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    level TEXT NOT NULL,
                    metadata TEXT
                )
            """)
            conn.commit()
    
    def log_post_attempt(self, tweet_text: str, seed_chunk_hash: str, 
                        status: str, twitter_id: Optional[str] = None,
                        error_message: Optional[str] = None,
                        generation_time_ms: Optional[int] = None,
                        account_id: Optional[str] = None,
                        metadata: Optional[dict] = None):
        """Log a tweet posting attempt."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO post_history 
                (tweet_text, seed_chunk_hash, status, twitter_id, error_message, 
                 generation_time_ms, account_id, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (tweet_text, seed_chunk_hash, status, twitter_id, error_message,
                  generation_time_ms, account_id, json.dumps(metadata) if metadata else None))
            conn.commit()
        
        logger.info("Post attempt logged", 
                   account_id=account_id, status=status, twitter_id=twitter_id, seed_chunk_hash=seed_chunk_hash)
    
    def log_system_event(self, event_type: str, message: str, level: str = "INFO",
                        metadata: Optional[dict] = None):
        """Log a system event."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO system_events (event_type, message, level, metadata)
                VALUES (?, ?, ?, ?)
            """, (event_type, message, level, json.dumps(metadata) if metadata else None))
            conn.commit()
        
        logger.info("System event logged", 
                   event_type=event_type, level=level, message=message)
    
    def get_recent_posts(self, limit: int = 50, account_filter: Optional[str] = None) -> List[dict]:
        """Get recent post history."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if account_filter:
                cursor = conn.execute("""
                    SELECT * FROM post_history 
                    WHERE account_id = ? OR account_id IS NULL
                    ORDER BY timestamp DESC 
                    LIMIT ?
                """, (account_filter, limit))
            else:
                cursor = conn.execute("""
                    SELECT * FROM post_history 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_recent_seed_hashes(self, limit: int = 50) -> List[str]:
        """Get seed chunk hashes from recent posts for deduplication."""
        try:
            # Ensure database exists
            self._init_db()
            
            with sqlite3.connect(self.db_path) as conn:
                # Check if table exists and has data
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM sqlite_master 
                    WHERE type='table' AND name='post_history'
                """)
                table_exists = cursor.fetchone()[0] > 0
                
                if not table_exists:
                    logger.debug("post_history table does not exist, returning empty list")
                    return []
                
                cursor = conn.execute("""
                    SELECT seed_chunk_hash FROM post_history 
                    WHERE status = 'success' AND seed_chunk_hash IS NOT NULL
                    ORDER BY timestamp DESC 
                    LIMIT ?
                """, (limit,))
                results = cursor.fetchall()
                hashes = [row[0] for row in results if row[0]]
                logger.debug("Retrieved recent seed hashes", count=len(hashes), limit=limit)
                return hashes
        except Exception as e:
            logger.error("Failed to get recent seed hashes", error=str(e), limit=limit)
            return []  # Always return empty list on error
    
    def get_success_rate(self, hours: int = 24, account_filter: Optional[str] = None) -> float:
        """Get posting success rate for the last N hours, optionally filtered by account."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        with sqlite3.connect(self.db_path) as conn:
            if account_filter:
                # Total attempts for account
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM post_history 
                    WHERE timestamp >= ? AND account_id = ?
                """, (cutoff_time, account_filter))
                total = cursor.fetchone()[0]
                
                if total == 0:
                    return 1.0
                
                # Successful posts for account
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM post_history 
                    WHERE timestamp >= ? AND account_id = ? AND status = 'success'
                """, (cutoff_time, account_filter))
                successful = cursor.fetchone()[0]
            else:
                # Total attempts
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM post_history 
                    WHERE timestamp >= ?
                """, (cutoff_time,))
                total = cursor.fetchone()[0]
                
                if total == 0:
                    return 1.0
                
                # Successful posts
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM post_history 
                    WHERE timestamp >= ? AND status = 'success'
                """, (cutoff_time,))
                successful = cursor.fetchone()[0]
            
            return successful / total
    
    def get_last_successful_post_time(self, account_id: Optional[str] = None) -> Optional[datetime]:
        """Get the timestamp of the most recent successful post."""
        with sqlite3.connect(self.db_path) as conn:
            if account_id:
                cursor = conn.execute("""
                    SELECT timestamp FROM post_history 
                    WHERE status = 'success' AND (account_id = ? OR account_id IS NULL)
                    ORDER BY timestamp DESC 
                    LIMIT 1
                """, (account_id,))
            else:
                cursor = conn.execute("""
                    SELECT timestamp FROM post_history 
                    WHERE status = 'success'
                    ORDER BY timestamp DESC 
                    LIMIT 1
                """)
            
            result = cursor.fetchone()
            if result:
                # Parse the timestamp string back to datetime
                timestamp_str = result[0]
                try:
                    return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    # Try parsing as SQLite DATETIME format
                    try:
                        return datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                    except (ValueError, TypeError):
                        return None
            return None
    
    def get_account_last_post_time(self, account_id: str) -> Optional[datetime]:
        """Get the timestamp of the most recent successful post for a specific account."""
        return self.get_last_successful_post_time(account_id=account_id)


class HealthChecker:
    """System health monitoring."""
    
    def __init__(self, cost_tracker: CostTracker, activity_logger: ActivityLogger):
        self.cost_tracker = cost_tracker
        self.activity_logger = activity_logger
    
    def check_health(self, deep: bool = False) -> Dict[str, any]:
        """Perform health check."""
        health_status = {
            "timestamp": datetime.now().isoformat(),
            "status": "healthy",
            "checks": {}
        }
        
        # Basic checks
        health_status["checks"]["config"] = self._check_config()
        health_status["checks"]["files"] = self._check_files()
        health_status["checks"]["cost_limits"] = self._check_cost_limits()
        
        if deep:
            health_status["checks"]["vector_db"] = self._check_vector_db()
            health_status["checks"]["api_keys"] = self._check_api_keys()
        
        # Determine overall status
        failed_checks = [k for k, v in health_status["checks"].items() if not v["healthy"]]
        if failed_checks:
            health_status["status"] = "unhealthy"
            health_status["failed_checks"] = failed_checks
        
        return health_status
    
    def _check_config(self) -> Dict[str, any]:
        """Check configuration files."""
        try:
            from app.deps import get_config
            config = get_config()
            return {"healthy": True, "message": "Configuration loaded successfully"}
        except Exception as e:
            return {"healthy": False, "message": f"Config error: {str(e)}"}
    
    def _check_files(self) -> Dict[str, any]:
        """Check required files exist."""
        try:
            # Check for account configurations instead of legacy files
            from app.account_manager import load_all_accounts
            accounts = load_all_accounts()
            
            if not accounts:
                return {"healthy": False, "message": "No account configurations found"}
            
            # Check that each account has required fields
            for account_id, account in accounts.items():
                if not account.get("persona"):
                    return {"healthy": False, "message": f"Account {account_id} missing persona"}
                if not account.get("exemplars"):
                    return {"healthy": False, "message": f"Account {account_id} missing exemplars"}
            
            return {"healthy": True, "message": f"All {len(accounts)} account configurations valid"}
        except Exception as e:
            return {"healthy": False, "message": f"Account configuration error: {str(e)}"}
    
    def _check_cost_limits(self) -> Dict[str, any]:
        """Check cost limits."""
        try:
            within_limit = self.cost_tracker.check_daily_limit()
            daily_cost = self.cost_tracker.get_daily_cost()
            
            return {
                "healthy": within_limit,
                "message": f"Daily cost: ${daily_cost:.2f}",
                "within_limit": within_limit
            }
        except Exception as e:
            return {"healthy": False, "message": f"Cost tracking error: {str(e)}"}
    
    def _check_vector_db(self) -> Dict[str, any]:
        """Check vector database connection."""
        try:
            from app.deps import get_vector_db
            client = get_vector_db()
            client.heartbeat()
            return {"healthy": True, "message": "Vector DB accessible"}
        except Exception as e:
            return {"healthy": False, "message": f"Vector DB error: {str(e)}"}
    
    def _check_api_keys(self) -> Dict[str, any]:
        """Check API key availability (not validity)."""
        import os
        
        required_keys = [
            "OPENAI_API_KEY",
            "TWITTER_BEARER_TOKEN",
            "TWITTER_API_KEY",
            "TWITTER_API_SECRET",
            "TWITTER_ACCESS_TOKEN",
            "TWITTER_ACCESS_TOKEN_SECRET"
        ]
        
        missing_keys = [key for key in required_keys if not os.getenv(key)]
        if missing_keys:
            return {"healthy": False, "message": f"Missing API keys: {missing_keys}"}
        
        return {"healthy": True, "message": "All API keys present"}