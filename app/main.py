"""Main FastAPI application for the Zen Kink Bot."""

"""
Main FastAPI application module - Core entry point for the Twitter bot web service.

This module serves as the primary web interface for the multi-account Twitter bot system.
It provides:
- Web dashboard UI for monitoring and control
- RESTful API endpoints for bot operations
- Health monitoring and emergency controls
- Account management interfaces
- Real-time status and metrics
- Manual tweet generation and posting

Key responsibilities:
1. Web Server: Hosts the FastAPI application with async lifecycle management
2. Dashboard UI: Renders the control panel interface using Jinja2 templates
3. API Endpoints: Provides REST APIs for all bot operations (posting, monitoring, config)
4. Account Routing: Handles multi-account operations with account-specific endpoints
5. Health Monitoring: Exposes health check endpoints for system monitoring
6. Emergency Controls: Implements emergency stop functionality for safety
7. Cost Tracking: Integrates with monitoring systems for API cost management
8. Logging: Structured logging with correlation IDs for debugging

The application follows a modular architecture where this main module orchestrates
various subsystems (generation, scheduling, monitoring, security) through dependency injection.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.account_manager import get_account, get_account_ids, load_all_accounts
from app.deps import get_config
from app.exceptions import ZenKinkBotException
from app.monitoring import ActivityLogger, CostTracker, HealthChecker

# Load environment variables from config/.env
load_dotenv("config/.env")

# Configure logging
logger = structlog.get_logger(__name__)

# Global instances
cost_tracker = None
activity_logger = None
health_checker = None
emergency_stop = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup application resources."""
    global cost_tracker, activity_logger, health_checker

    try:
        # Initialize monitoring components
        config = get_config()
        daily_limit = config.get("cost_limits", {}).get("daily_limit_usd", 10.0)

        cost_tracker = CostTracker(daily_limit=daily_limit)
        activity_logger = ActivityLogger()
        health_checker = HealthChecker(cost_tracker, activity_logger)

        # Start the tweet scheduler for automatic posting
        from app.scheduler import start_scheduler

        start_scheduler()
        logger.info("Tweet scheduler started - automatic posting enabled")

        # Log startup
        activity_logger.log_system_event(
            "startup", "Application started successfully with automatic posting"
        )
        logger.info("Zen Kink Bot started successfully")

        yield

    except Exception as e:
        logger.error("Failed to initialize application", error=str(e))
        raise
    finally:
        # Cleanup scheduler
        try:
            from app.scheduler import stop_scheduler

            stop_scheduler()
            logger.info("Tweet scheduler stopped")
        except Exception as e:
            logger.error("Error stopping scheduler during cleanup", error=str(e))

        # Cleanup monitoring
        if activity_logger:
            activity_logger.log_system_event("shutdown", "Application shutting down")
        logger.info("Zen Kink Bot shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Zen Kink Bot",
    description="Autonomous Twitter bot blending Eckhart Tolle and Carolyn Elliott philosophies",
    version="0.1.0",
    lifespan=lifespan,
)

# Templates and static files
templates = Jinja2Templates(directory="ui_templates")

# Mount static files if directory exists
static_dir = Path("ui_templates/static")
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.exception_handler(ZenKinkBotException)
async def bot_exception_handler(request: Request, exc: ZenKinkBotException):
    """Handle custom bot exceptions."""
    logger.error("Bot exception occurred", exception=str(exc), path=request.url.path)
    return JSONResponse(status_code=500, content={"error": f"Bot error: {str(exc)}"})


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions."""
    logger.error(
        "Unexpected exception occurred", exception=str(exc), path=request.url.path
    )
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


@app.get("/")
async def dashboard(request: Request, account_id: Optional[str] = None):
    """Main dashboard page with optional account selection."""
    try:
        # Load all accounts
        accounts = load_all_accounts()

        # If no account specified or invalid account, use first available
        if not account_id or account_id not in accounts:
            if accounts:
                account_id = list(accounts.keys())[0]
            else:
                raise HTTPException(status_code=500, detail="No accounts configured")

        account = accounts[account_id]

        # Get system status
        health_status = health_checker.check_health(deep=False)
        recent_posts = activity_logger.get_recent_posts(
            limit=5, account_filter=account_id
        )
        daily_cost = cost_tracker.get_daily_cost()
        success_rate = activity_logger.get_success_rate(
            hours=24, account_filter=account_id
        )

        # Get account-specific data
        persona = account.get("persona", "")
        exemplars = account.get("exemplars", [])

        # Get scheduler status
        from app.scheduler import get_scheduler_status

        scheduler_status = get_scheduler_status()

        context = {
            "request": request,
            "current_account_id": account_id,
            "current_account": account,
            "all_accounts": accounts,
            "health_status": health_status,
            "recent_posts": recent_posts,
            "daily_cost": daily_cost,
            "cost_limit": cost_tracker.daily_limit,
            "success_rate": success_rate,
            "persona": persona,
            "exemplars": exemplars,
            "emergency_stop": emergency_stop,
            "scheduler": scheduler_status,
        }

        return templates.TemplateResponse("dashboard.html", context)

    except Exception as e:
        logger.error("Dashboard error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Dashboard error: {str(e)}")


@app.get("/health")
async def health_check():
    """Basic health check endpoint."""
    try:
        health_status = health_checker.check_health(deep=False)
        status_code = 200 if health_status["status"] == "healthy" else 503
        return JSONResponse(content=health_status, status_code=status_code)
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return JSONResponse(
            content={"status": "unhealthy", "error": str(e)}, status_code=503
        )


@app.get("/health/deep")
async def deep_health_check():
    """Deep health check with external dependencies."""
    try:
        health_status = health_checker.check_health(deep=True)
        status_code = 200 if health_status["status"] == "healthy" else 503
        return JSONResponse(content=health_status, status_code=status_code)
    except Exception as e:
        logger.error("Deep health check failed", error=str(e))
        return JSONResponse(
            content={"status": "unhealthy", "error": str(e)}, status_code=503
        )


@app.post("/emergency-stop")
async def emergency_stop_toggle():
    """Toggle emergency stop state."""
    global emergency_stop
    emergency_stop = not emergency_stop

    status = "activated" if emergency_stop else "deactivated"
    activity_logger.log_system_event(
        "emergency_stop",
        f"Emergency stop {status}",
        level="WARNING" if emergency_stop else "INFO",
    )

    logger.warning("Emergency stop toggled", emergency_stop=emergency_stop)

    return {"emergency_stop": emergency_stop, "message": f"Emergency stop {status}"}


@app.get("/api/status")
async def get_status():
    """Get current system status as JSON."""
    try:
        health_status = health_checker.check_health(deep=False)
        recent_posts = activity_logger.get_recent_posts(limit=1)

        # Get scheduler status
        from app.scheduler import get_scheduler_status

        scheduler_status = get_scheduler_status()

        last_post = recent_posts[0] if recent_posts else None

        return {
            "status": "active" if not emergency_stop else "stopped",
            "health": health_status["status"],
            "last_post": last_post,
            "emergency_stop": emergency_stop,
            "daily_cost": cost_tracker.get_daily_cost(),
            "cost_limit": cost_tracker.daily_limit,
            "success_rate": activity_logger.get_success_rate(hours=24),
            "scheduler": scheduler_status,
        }
    except Exception as e:
        logger.error("Status API error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/force-post")
async def force_post():
    """Force generate and post a tweet immediately."""
    if emergency_stop:
        return HTMLResponse(
            """
        <div class="mt-4 p-4 bg-red-50 border border-red-200 rounded">
            <h4 class="font-medium text-red-800 mb-2">Cannot Post:</h4>
            <p class="text-sm text-red-700">Emergency stop is active</p>
        </div>
        """
        )

    try:
        # Import here to avoid circular imports
        from app.generation import generate_and_post_tweet

        logger.info("Starting forced tweet generation and posting")
        result = await generate_and_post_tweet()

        if result.get("status") == "success":
            html = f"""
            <div class="mt-4 p-4 bg-green-50 border border-green-200 rounded">
                <h4 class="font-medium text-green-800 mb-2">Tweet Posted Successfully!</h4>
                <p class="text-sm bg-white p-3 rounded border">{result.get('tweet_text', '')}</p>
                <div class="mt-2 text-xs text-green-600">
                    Length: {result.get('character_count', 0)}/280 • 
                    Source: {result.get('seed_source', 'Unknown')} • 
                    Generation time: {result.get('generation_time_ms', 0)}ms
                    {' • Shortened' if result.get('was_shortened') else ''}
                    {f' • Twitter ID: {result.get("twitter_id")}' if result.get('twitter_id') else ''}
                </div>
            </div>
            """
        else:
            html = f"""
            <div class="mt-4 p-4 bg-red-50 border border-red-200 rounded">
                <h4 class="font-medium text-red-800 mb-2">Post Failed:</h4>
                <p class="text-sm text-red-700">{result.get('error', 'Unknown error')}</p>
            </div>
            """

        return HTMLResponse(html)

    except Exception as e:
        logger.error("Force post failed", error=str(e))
        html = f"""
        <div class="mt-4 p-4 bg-red-50 border border-red-200 rounded">
            <h4 class="font-medium text-red-800 mb-2">Force Post Failed:</h4>
            <p class="text-sm text-red-700">{str(e)}</p>
        </div>
        """
        return HTMLResponse(html)


@app.get("/api/logs")
async def get_logs(limit: int = 100):
    """Get recent activity logs."""
    try:
        posts = activity_logger.get_recent_posts(limit=limit)
        return {"posts": posts}
    except Exception as e:
        logger.error("Logs API error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/costs")
async def get_costs():
    """Get cost breakdown and statistics."""
    try:
        daily_cost = cost_tracker.get_daily_cost()
        cost_breakdown = cost_tracker.get_cost_breakdown(days=7)

        return {
            "daily_cost": daily_cost,
            "daily_limit": cost_tracker.daily_limit,
            "within_limit": cost_tracker.check_daily_limit(),
            "breakdown_7_days": cost_breakdown,
        }
    except Exception as e:
        logger.error("Costs API error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/persona")
async def update_persona(request: Request):
    """Update the bot's persona (global fallback)."""
    try:
        form = await request.form()
        new_persona = form.get("persona", "").strip()

        if not new_persona:
            raise HTTPException(status_code=400, detail="Persona cannot be empty")

        # Validate content
        from app.security import validate_user_input

        if not validate_user_input(new_persona, "persona"):
            raise HTTPException(
                status_code=400, detail="Persona contains inappropriate content"
            )

        # Save to file
        persona_path = Path("data/persona.txt")
        persona_path.write_text(new_persona)

        logger.info("Global persona updated", length=len(new_persona))
        activity_logger.log_system_event("persona_updated", "User updated bot persona")

        return {"success": True, "message": "Persona updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update persona", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to update persona: {str(e)}"
        )


@app.post("/api/persona/{account_id}")
async def update_account_persona(account_id: str, request: Request):
    """Update a specific account's persona."""
    try:
        # Verify account exists
        account = get_account(account_id)
        if not account:
            raise HTTPException(
                status_code=404, detail=f"Account {account_id} not found"
            )

        form = await request.form()
        new_persona = form.get("persona", "").strip()

        if not new_persona:
            raise HTTPException(status_code=400, detail="Persona cannot be empty")

        # Validate content
        from app.security import validate_user_input

        if not validate_user_input(new_persona, "persona"):
            raise HTTPException(
                status_code=400, detail="Persona contains inappropriate content"
            )

        # Update account configuration
        account["persona"] = new_persona

        # Save account configuration
        from app.account_manager import get_account_manager

        account_manager = get_account_manager()
        success = account_manager.save_account(account)

        if not success:
            raise HTTPException(
                status_code=500, detail="Failed to save account configuration"
            )

        logger.info(
            "Account persona updated", account_id=account_id, length=len(new_persona)
        )
        activity_logger.log_system_event(
            "persona_updated", f"User updated persona for account {account_id}"
        )

        return {"success": True, "message": f"Persona updated for {account_id}"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to update account persona", account_id=account_id, error=str(e)
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to update persona: {str(e)}"
        )


@app.post("/api/exemplars")
async def add_exemplar(request: Request):
    """Add a new exemplar tweet (global fallback)."""
    try:
        form = await request.form()
        tweet_text = form.get("tweet_text", "").strip()

        if not tweet_text:
            raise HTTPException(status_code=400, detail="Tweet text cannot be empty")

        # Validate content
        from app.security import validate_user_input

        if not validate_user_input(tweet_text, "exemplar"):
            raise HTTPException(
                status_code=400, detail="Tweet contains inappropriate content"
            )

        # Load existing exemplars
        import json

        exemplars_path = Path("data/exemplars.json")

        if exemplars_path.exists():
            with open(exemplars_path) as f:
                exemplars = json.load(f)
        else:
            exemplars = []

        # Add new exemplar
        new_id = max([e.get("id", 0) for e in exemplars], default=0) + 1
        new_exemplar = {
            "id": new_id,
            "text": tweet_text,
            "created_at": datetime.now().isoformat(),
        }

        exemplars.append(new_exemplar)

        # Save back to file
        with open(exemplars_path, "w") as f:
            json.dump(exemplars, f, indent=2)

        logger.info("Global exemplar added", id=new_id, text=tweet_text[:50])
        activity_logger.log_system_event(
            "exemplar_added", f"Added exemplar: {tweet_text[:50]}..."
        )

        return HTMLResponse(
            f"""
        <div class="flex items-start justify-between p-3 bg-gray-50 rounded border">
            <div class="flex-1">
                <p class="text-sm">{tweet_text}</p>
            </div>
            <button 
                hx-delete="/api/exemplars/{new_id}"
                hx-target="closest div"
                hx-swap="outerHTML"
                hx-confirm="Delete this exemplar?"
                class="ml-2 text-red-500 hover:text-red-700">
                ×
            </button>
        </div>
        """
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to add exemplar", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to add exemplar: {str(e)}")


@app.post("/api/exemplars/{account_id}")
async def add_account_exemplar(account_id: str, request: Request):
    """Add a new exemplar tweet for a specific account."""
    try:
        # Verify account exists
        account = get_account(account_id)
        if not account:
            raise HTTPException(
                status_code=404, detail=f"Account {account_id} not found"
            )

        form = await request.form()
        tweet_text = form.get("tweet_text", "").strip()

        if not tweet_text:
            raise HTTPException(status_code=400, detail="Tweet text cannot be empty")

        # Validate content
        from app.security import validate_user_input

        if not validate_user_input(tweet_text, "exemplar"):
            raise HTTPException(
                status_code=400, detail="Tweet contains inappropriate content"
            )

        # Get existing exemplars from account
        exemplars = account.get("exemplars", [])

        # Add new exemplar
        new_id = max([e.get("id", 0) for e in exemplars], default=0) + 1
        new_exemplar = {
            "id": new_id,
            "text": tweet_text,
            "created_at": datetime.now().isoformat(),
        }

        exemplars.append(new_exemplar)
        account["exemplars"] = exemplars

        # Save account configuration
        from app.account_manager import get_account_manager

        account_manager = get_account_manager()
        success = account_manager.save_account(account)

        if not success:
            raise HTTPException(
                status_code=500, detail="Failed to save account configuration"
            )

        logger.info(
            "Account exemplar added",
            account_id=account_id,
            id=new_id,
            text=tweet_text[:50],
        )
        activity_logger.log_system_event(
            "exemplar_added", f"Added exemplar to {account_id}: {tweet_text[:50]}..."
        )

        return HTMLResponse(
            f"""
        <div class="flex items-start justify-between p-3 bg-gray-50 rounded border">
            <div class="flex-1">
                <p class="text-sm">{tweet_text}</p>
            </div>
            <button 
                hx-delete="/api/exemplars/{account_id}/{new_id}"
                hx-target="closest div"
                hx-swap="outerHTML"
                hx-confirm="Delete this exemplar?"
                class="ml-2 text-red-500 hover:text-red-700">
                ×
            </button>
        </div>
        """
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to add account exemplar", account_id=account_id, error=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Failed to add exemplar: {str(e)}")


@app.delete("/api/exemplars/{exemplar_id}")
async def delete_exemplar(exemplar_id: int):
    """Delete an exemplar tweet (global fallback)."""
    try:
        import json

        exemplars_path = Path("data/exemplars.json")

        if not exemplars_path.exists():
            raise HTTPException(status_code=404, detail="No exemplars found")

        with open(exemplars_path) as f:
            exemplars = json.load(f)

        # Remove exemplar with matching ID
        exemplars = [e for e in exemplars if e.get("id") != exemplar_id]

        # Save back to file
        with open(exemplars_path, "w") as f:
            json.dump(exemplars, f, indent=2)

        logger.info("Global exemplar deleted", id=exemplar_id)
        activity_logger.log_system_event(
            "exemplar_deleted", f"Deleted exemplar ID: {exemplar_id}"
        )

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete exemplar", exemplar_id=exemplar_id, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to delete exemplar: {str(e)}"
        )


@app.delete("/api/exemplars/{account_id}/{exemplar_id}")
async def delete_account_exemplar(account_id: str, exemplar_id: int):
    """Delete an exemplar tweet from a specific account."""
    try:
        # Verify account exists
        account = get_account(account_id)
        if not account:
            raise HTTPException(
                status_code=404, detail=f"Account {account_id} not found"
            )

        # Get existing exemplars from account
        exemplars = account.get("exemplars", [])

        # Remove exemplar with matching ID
        exemplars = [e for e in exemplars if e.get("id") != exemplar_id]
        account["exemplars"] = exemplars

        # Save account configuration
        from app.account_manager import get_account_manager

        account_manager = get_account_manager()
        success = account_manager.save_account(account)

        if not success:
            raise HTTPException(
                status_code=500, detail="Failed to save account configuration"
            )

        logger.info("Account exemplar deleted", account_id=account_id, id=exemplar_id)
        activity_logger.log_system_event(
            "exemplar_deleted", f"Deleted exemplar ID {exemplar_id} from {account_id}"
        )

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to delete account exemplar",
            account_id=account_id,
            exemplar_id=exemplar_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to delete exemplar: {str(e)}"
        )


@app.get("/api/search-chunks")
async def search_chunks(query: str, limit: int = 10):
    """Search knowledge base chunks."""
    try:
        from app.vector_search import search_knowledge_base

        if not query.strip():
            return HTMLResponse(
                "<p class='text-gray-500 text-sm'>Enter a search term to explore the knowledge base</p>"
            )

        results = search_knowledge_base(query, limit=limit)

        if not results:
            return HTMLResponse("<p class='text-gray-500 text-sm'>No results found</p>")

        # Build HTML response
        html_parts = []
        for result in results:
            html_parts.append(
                f"""
            <div class="p-3 bg-gray-50 rounded border">
                <div class="flex justify-between items-start mb-2">
                    <span class="text-xs text-gray-500">{result['source_title']} - Chunk {result['chunk_index']}</span>
                    <span class="text-xs text-blue-600">Similarity: {result['similarity']}</span>
                </div>
                <p class="text-sm whitespace-pre-wrap">{result['full_text']}</p>
                <div class="text-xs text-gray-400 mt-1">{result['word_count']} words</div>
            </div>
            """
            )

        return HTMLResponse("\n".join(html_parts))

    except Exception as e:
        logger.error("Chunk search failed", query=query, error=str(e))
        return HTMLResponse(
            f"<p class='text-red-500 text-sm'>Search failed: {str(e)}</p>"
        )


@app.post("/api/test-generation")
async def test_generation(request: Request):
    """Generate a test tweet without posting."""
    try:
        form = await request.form()
        custom_persona = form.get("persona")

        from app.generation import generate_test_tweet

        result = await generate_test_tweet(
            custom_persona=custom_persona if custom_persona else None
        )

        if result["status"] == "success" and result.get("tweet_text"):
            html = f"""
            <div class="mt-4 p-4 bg-green-50 border border-green-200 rounded">
                <h4 class="font-medium text-green-800 mb-2">Test Tweet Generated:</h4>
                <p class="text-sm bg-white p-3 rounded border">{result['tweet_text']}</p>
                <div class="mt-2 text-xs text-green-600">
                    Length: {result['character_count']}/280 • 
                    Source: {result['seed_source']} • 
                    Generation time: {result['generation_time_ms']}ms
                    {' • Shortened' if result.get('was_shortened') else ''}
                </div>
            </div>
            """
        elif result["status"] == "success" and not result.get("tweet_text"):
            html = f"""
            <div class="mt-4 p-4 bg-yellow-50 border border-yellow-200 rounded">
                <h4 class="font-medium text-yellow-800 mb-2">Empty Tweet Generated:</h4>
                <p class="text-sm text-yellow-700">Tweet generation completed but returned empty text. Check model configuration and prompts.</p>
                <div class="mt-2 text-xs text-yellow-600">
                    Source: {result.get('seed_source', 'Unknown')} • 
                    Generation time: {result.get('generation_time_ms', 0)}ms
                </div>
            </div>
            """
        else:
            html = f"""
            <div class="mt-4 p-4 bg-red-50 border border-red-200 rounded">
                <h4 class="font-medium text-red-800 mb-2">Generation Failed:</h4>
                <p class="text-sm text-red-700">{result.get('error', 'Unknown error')}</p>
            </div>
            """

        return HTMLResponse(html)

    except Exception as e:
        logger.error("Test generation failed", error=str(e))
        html = f"""
        <div class="mt-4 p-4 bg-red-50 border border-red-200 rounded">
            <h4 class="font-medium text-red-800 mb-2">Test Failed:</h4>
            <p class="text-sm text-red-700">{str(e)}</p>
        </div>
        """
        return HTMLResponse(html)


# Multi-account API endpoints
@app.get("/api/accounts")
async def get_accounts():
    """Get list of all accounts."""
    try:
        accounts = load_all_accounts()
        account_list = []

        for account_id, account_config in accounts.items():
            account_info = {
                "account_id": account_id,
                "display_name": account_config.get("display_name", account_id),
                "vector_collection": account_config.get("vector_collection"),
                "has_credentials": bool(account_config.get("twitter_credentials")),
            }
            account_list.append(account_info)

        return {"accounts": account_list}
    except Exception as e:
        logger.error("Get accounts API error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/status/{account_id}")
async def get_account_status(account_id: str):
    """Get current status for a specific account."""
    try:
        # Verify account exists
        account = get_account(account_id)
        if not account:
            raise HTTPException(
                status_code=404, detail=f"Account {account_id} not found"
            )

        health_status = health_checker.check_health(deep=False)
        recent_posts = activity_logger.get_recent_posts(
            limit=5, account_filter=account_id
        )

        # Get scheduler status
        from app.scheduler import get_scheduler_status

        scheduler_status = get_scheduler_status()

        last_post = recent_posts[0] if recent_posts else None

        return {
            "account_id": account_id,
            "display_name": account.get("display_name", account_id),
            "status": "active" if not emergency_stop else "stopped",
            "health": health_status["status"],
            "last_post": last_post,
            "recent_posts": recent_posts,
            "emergency_stop": emergency_stop,
            "success_rate": activity_logger.get_success_rate(hours=24),
            "scheduler": scheduler_status,
            "vector_collection": account.get("vector_collection"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Account status API error", account_id=account_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/force-post/{account_id}")
async def force_post_account(account_id: str):
    """Force generate and post a tweet for a specific account."""
    try:
        # Verify account exists
        account = get_account(account_id)
        if not account:
            raise HTTPException(
                status_code=404, detail=f"Account {account_id} not found"
            )

        if emergency_stop:
            return HTMLResponse(
                f"""
            <div class="mt-4 p-4 bg-red-50 border border-red-200 rounded">
                <h4 class="font-medium text-red-800 mb-2">Cannot Post for {account_id}:</h4>
                <p class="text-sm text-red-700">Emergency stop is active</p>
            </div>
            """
            )

        # Import here to avoid circular imports
        from app.generation import generate_and_post_tweet

        logger.info(
            "Starting forced tweet generation and posting", account_id=account_id
        )
        result = await generate_and_post_tweet(account_id=account_id)

        if result.get("status") == "success":
            html = f"""
            <div class="mt-4 p-4 bg-green-50 border border-green-200 rounded">
                <h4 class="font-medium text-green-800 mb-2">Tweet Posted Successfully for {account_id}!</h4>
                <p class="text-sm bg-white p-3 rounded border">{result.get('tweet_text', '')}</p>
                <div class="mt-2 text-xs text-green-600">
                    Length: {result.get('character_count', 0)}/280 • 
                    Source: {result.get('seed_source', 'Unknown')} • 
                    Generation time: {result.get('generation_time_ms', 0)}ms
                    {' • Shortened' if result.get('was_shortened') else ''}
                    {f' • Twitter ID: {result.get("twitter_id")}' if result.get('twitter_id') else ''}
                </div>
            </div>
            """
        else:
            html = f"""
            <div class="mt-4 p-4 bg-red-50 border border-red-200 rounded">
                <h4 class="font-medium text-red-800 mb-2">Post Failed for {account_id}:</h4>
                <p class="text-sm text-red-700">{result.get('error', 'Unknown error')}</p>
            </div>
            """

        return HTMLResponse(html)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Force post failed", account_id=account_id, error=str(e))
        html = f"""
        <div class="mt-4 p-4 bg-red-50 border border-red-200 rounded">
            <h4 class="font-medium text-red-800 mb-2">Force Post Failed for {account_id}:</h4>
            <p class="text-sm text-red-700">{str(e)}</p>
        </div>
        """
        return HTMLResponse(html)


@app.post("/api/test-generation/{account_id}")
async def test_generation_account(account_id: str, request: Request):
    """Generate a test tweet for a specific account without posting."""
    try:
        # Verify account exists
        account = get_account(account_id)
        if not account:
            raise HTTPException(
                status_code=404, detail=f"Account {account_id} not found"
            )

        form = await request.form()
        custom_persona = form.get("persona")

        from app.generation import generate_test_tweet

        result = await generate_test_tweet(
            custom_persona=custom_persona if custom_persona else None,
            account_id=account_id,
        )

        if result["status"] == "success" and result.get("tweet_text"):
            html = f"""
            <div class="mt-4 p-4 bg-green-50 border border-green-200 rounded">
                <h4 class="font-medium text-green-800 mb-2">Test Tweet Generated for {account_id}:</h4>
                <p class="text-sm bg-white p-3 rounded border">{result['tweet_text']}</p>
                <div class="mt-2 text-xs text-green-600">
                    Length: {result['character_count']}/280 • 
                    Source: {result['seed_source']} • 
                    Generation time: {result['generation_time_ms']}ms
                    {' • Shortened' if result.get('was_shortened') else ''}
                </div>
            </div>
            """
        elif result["status"] == "success" and not result.get("tweet_text"):
            html = f"""
            <div class="mt-4 p-4 bg-yellow-50 border border-yellow-200 rounded">
                <h4 class="font-medium text-yellow-800 mb-2">Empty Tweet Generated for {account_id}:</h4>
                <p class="text-sm text-yellow-700">Tweet generation completed but returned empty text. Check model configuration and prompts.</p>
                <div class="mt-2 text-xs text-yellow-600">
                    Source: {result.get('seed_source', 'Unknown')} • 
                    Generation time: {result.get('generation_time_ms', 0)}ms
                </div>
            </div>
            """
        else:
            html = f"""
            <div class="mt-4 p-4 bg-red-50 border border-red-200 rounded">
                <h4 class="font-medium text-red-800 mb-2">Generation Failed for {account_id}:</h4>
                <p class="text-sm text-red-700">{result.get('error', 'Unknown error')}</p>
            </div>
            """

        return HTMLResponse(html)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Test generation failed", account_id=account_id, error=str(e))
        html = f"""
        <div class="mt-4 p-4 bg-red-50 border border-red-200 rounded">
            <h4 class="font-medium text-red-800 mb-2">Test Failed for {account_id}:</h4>
            <p class="text-sm text-red-700">{str(e)}</p>
        </div>
        """
        return HTMLResponse(html)


@app.get("/api/search-chunks/{account_id}")
async def search_chunks_account(account_id: str, query: str, limit: int = 10):
    """Search knowledge base chunks for a specific account."""
    try:
        # Verify account exists
        account = get_account(account_id)
        if not account:
            raise HTTPException(
                status_code=404, detail=f"Account {account_id} not found"
            )

        from app.vector_search import search_knowledge_base

        if not query.strip():
            return HTMLResponse(
                f"<p class='text-gray-500 text-sm'>Enter a search term to explore the knowledge base for {account_id}</p>"
            )

        results = search_knowledge_base(query, limit=limit, account_id=account_id)

        if not results:
            return HTMLResponse(
                f"<p class='text-gray-500 text-sm'>No results found for {account_id}</p>"
            )

        # Build HTML response
        html_parts = []
        for result in results:
            html_parts.append(
                f"""
            <div class="p-3 bg-gray-50 rounded border">
                <div class="flex justify-between items-start mb-2">
                    <span class="text-xs text-gray-500">{result['source_title']} - Chunk {result['chunk_index']}</span>
                    <span class="text-xs text-blue-600">Similarity: {result['similarity']}</span>
                </div>
                <p class="text-sm whitespace-pre-wrap">{result['full_text']}</p>
                <div class="text-xs text-gray-400 mt-1">{result['word_count']} words</div>
            </div>
            """
            )

        return HTMLResponse("\n".join(html_parts))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Chunk search failed", account_id=account_id, query=query, error=str(e)
        )
        return HTMLResponse(
            f"<p class='text-red-500 text-sm'>Search failed for {account_id}: {str(e)}</p>"
        )


@app.post("/api/resume-scheduler")
async def resume_scheduler():
    """Resume the scheduler if it's paused."""
    try:
        from app.scheduler import get_scheduler

        scheduler = get_scheduler()
        scheduler.resume()

        logger.info("Scheduler resume requested via API")
        return {"success": True, "message": "Scheduler resumed"}
    except Exception as e:
        logger.error("Failed to resume scheduler", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to resume scheduler: {str(e)}"
        )


@app.post("/api/pause-scheduler")
async def pause_scheduler():
    """Pause the scheduler."""
    try:
        from app.scheduler import get_scheduler

        scheduler = get_scheduler()
        scheduler.pause()

        logger.info("Scheduler pause requested via API")
        return {"success": True, "message": "Scheduler paused"}
    except Exception as e:
        logger.error("Failed to pause scheduler", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to pause scheduler: {str(e)}"
        )


@app.post("/api/restart-scheduler")
async def restart_scheduler():
    """Restart the scheduler completely."""
    try:
        from app.scheduler import start_scheduler, stop_scheduler

        logger.info("Restarting scheduler via API")
        stop_scheduler()
        await asyncio.sleep(2)  # Give it time to stop
        start_scheduler()

        return {"success": True, "message": "Scheduler restarted"}
    except Exception as e:
        logger.error("Failed to restart scheduler", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to restart scheduler: {str(e)}"
        )


@app.get("/api/platform-info/{account_id}")
async def get_platform_info_api(account_id: str):
    """Get platform information for a specific account."""
    try:
        # Verify account exists
        account = get_account(account_id)
        if not account:
            raise HTTPException(
                status_code=404, detail=f"Account {account_id} not found"
            )

        from app.multi_platform_poster import get_platform_info

        platform_info = get_platform_info(account_id=account_id)

        return platform_info
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Platform info API error", account_id=account_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/test-connections/{account_id}")
async def test_platform_connections(account_id: str):
    """Test connections to all platforms for a specific account."""
    try:
        # Verify account exists
        account = get_account(account_id)
        if not account:
            raise HTTPException(
                status_code=404, detail=f"Account {account_id} not found"
            )

        from app.multi_platform_poster import test_all_platform_connections

        connection_results = test_all_platform_connections(account_id=account_id)

        return connection_results
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Connection test API error", account_id=account_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/force-post-platform/{account_id}/{platform}")
async def force_post_single_platform(account_id: str, platform: str):
    """Force generate and post to a specific platform only."""
    try:
        # Verify account exists
        account = get_account(account_id)
        if not account:
            raise HTTPException(
                status_code=404, detail=f"Account {account_id} not found"
            )

        # Verify platform is enabled for this account
        enabled_platforms = account.get("posting_platforms", ["twitter"])
        if platform not in enabled_platforms:
            raise HTTPException(
                status_code=400,
                detail=f"Platform {platform} not enabled for account {account_id}",
            )

        if emergency_stop:
            return HTMLResponse(
                f"""
            <div class="mt-4 p-4 bg-red-50 border border-red-200 rounded">
                <h4 class="font-medium text-red-800 mb-2">Cannot Post to {platform.title()} for {account_id}:</h4>
                <p class="text-sm text-red-700">Emergency stop is active</p>
            </div>
            """
            )

        # Generate content first
        from app.generation import TweetGenerator
        from app.security import ContentFilter

        generator = TweetGenerator(account_id=account_id)
        generation_result = generator.generate_tweet()

        # Filter content
        content_filter = ContentFilter()
        if not content_filter.is_content_safe(generation_result["tweet_text"]):
            raise HTTPException(
                status_code=400, detail="Generated content failed safety filters"
            )

        # Post to specific platform
        from app.multi_platform_poster import MultiPlatformPoster

        multi_poster = MultiPlatformPoster(account_id=account_id)
        result = await multi_poster.post_to_platform(
            platform, generation_result["tweet_text"]
        )

        if result.get("status") in ["posted", "simulated"]:
            html = f"""
            <div class="mt-4 p-4 bg-green-50 border border-green-200 rounded">
                <h4 class="font-medium text-green-800 mb-2">{platform.title()} Post Successful for {account_id}!</h4>
                <p class="text-sm bg-white p-3 rounded border">{generation_result.get('tweet_text', '')}</p>
                <div class="mt-2 text-xs text-green-600">
                    Platform: {platform.title()} • 
                    Length: {generation_result.get('character_count', 0)} chars • 
                    {f'Post ID: {result.get("post_id")}' if result.get('post_id') else 'Simulated'}
                </div>
            </div>
            """
        else:
            html = f"""
            <div class="mt-4 p-4 bg-red-50 border border-red-200 rounded">
                <h4 class="font-medium text-red-800 mb-2">{platform.title()} Post Failed for {account_id}:</h4>
                <p class="text-sm text-red-700">{result.get('error', 'Unknown error')}</p>
            </div>
            """

        return HTMLResponse(html)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Single platform force post failed",
            account_id=account_id,
            platform=platform,
            error=str(e),
        )
        html = f"""
        <div class="mt-4 p-4 bg-red-50 border border-red-200 rounded">
            <h4 class="font-medium text-red-800 mb-2">{platform.title()} Post Failed for {account_id}:</h4>
            <p class="text-sm text-red-700">{str(e)}</p>
        </div>
        """
        return HTMLResponse(html)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
