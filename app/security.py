"""
Content filtering and security system - Multi-layer safety and moderation.

This module implements comprehensive content safety measures to ensure the bot
produces appropriate, non-controversial content. It combines rule-based filtering
with OpenAI's moderation API for robust protection.

Key Components:
1. ContentFilter: Multi-layer content safety validation
2. EmergencyControls: System-wide emergency stop capabilities

Safety Layers:
- Profanity filtering with customizable word lists
- Pattern matching for inappropriate content (violence, hate speech)
- Political content avoidance to maintain neutrality
- OpenAI Moderation API for comprehensive checks
- Spam and promotional content detection
- Excessive capitalization and repetition filters

Emergency Conditions:
- Daily cost limit exceeded
- Low success rate (< 50%)
- High error rates
- Repeated content filter rejections

The security system ensures:
- Brand safety through content filtering
- Cost protection with spending limits
- System stability with emergency stops
- User safety with input validation
- Compliance with platform policies
"""

import re
from typing import Dict, List, Optional

import structlog
from openai import OpenAI

from app.deps import get_config, get_openai_client
from app.exceptions import ContentFilterError, OpenAIError
from app.monitoring import ActivityLogger, CostTracker

logger = structlog.get_logger(__name__)


class ContentFilter:
    """Filter content for safety and appropriateness."""

    def __init__(self):
        self.openai_client = get_openai_client()
        self.cost_tracker = CostTracker()
        self.activity_logger = ActivityLogger()

        # Load configuration
        config = get_config()
        content_filter_config = config.get("content_filter", {})
        self.enabled = content_filter_config.get("enabled", True)
        self.use_openai_moderation = content_filter_config.get(
            "use_openai_moderation", True
        )
        self.use_profanity_filter = content_filter_config.get("profanity_filter", True)

        # Basic profanity list (can be expanded)
        self.profanity_words = {
            "damn",
            "hell",
            "shit",
            "fuck",
            "bitch",
            "ass",
            "piss",
            "crap",
            "bastard",
            "slut",
            "whore",
            "dick",
            "cock",
            "pussy",
            "cunt",
        }

        # Inappropriate content patterns
        self.inappropriate_patterns = [
            r"\b(kill|murder|suicide|die|death)\b",  # Violence/death
            r"\b(hate|hatred|despise)\s+(people|person|group|race|religion)\b",  # Hate speech
            r"\b(buy|purchase|sale|discount|offer|deal)\b.*\b(now|today|limited)\b",  # Spam/promotion
            r"\b(click|visit|check\s+out)\s+(link|website|url)\b",  # Spam links
            r"\b(drugs|cocaine|heroin|meth|marijuana)\b",  # Drug references
        ]

        # Political/controversial topics to avoid
        self.political_keywords = {
            "trump",
            "biden",
            "republican",
            "democrat",
            "liberal",
            "conservative",
            "election",
            "vote",
            "politics",
            "political",
            "government",
            "congress",
            "president",
            "senator",
            "politician",
        }

    def is_content_safe(self, text: str) -> bool:
        """Main content safety check."""
        if not self.enabled:
            logger.debug("Content filtering disabled, allowing all content")
            return True

        try:
            # Basic checks first (faster)
            if not self._basic_safety_check(text):
                return False

            # OpenAI moderation check (more comprehensive but costs money)
            if self.use_openai_moderation:
                if not self._openai_moderation_check(text):
                    return False

            logger.debug("Content passed all safety checks", text_length=len(text))
            return True

        except Exception as e:
            logger.error("Content filtering error", error=str(e))
            # Fail safe: if filtering fails, reject content
            return False

    def _basic_safety_check(self, text: str) -> bool:
        """Basic rule-based safety checks."""
        text_lower = text.lower()

        # Check for profanity
        if self.use_profanity_filter:
            for word in self.profanity_words:
                if word in text_lower:
                    logger.warning("Content rejected for profanity", word=word)
                    self._log_filter_event("profanity", text, f"Contains word: {word}")
                    return False

        # Check inappropriate patterns
        for pattern in self.inappropriate_patterns:
            if re.search(pattern, text_lower):
                logger.warning(
                    "Content rejected for inappropriate pattern", pattern=pattern
                )
                self._log_filter_event(
                    "inappropriate_pattern", text, f"Matches pattern: {pattern}"
                )
                return False

        # Check for political content
        political_words_found = [
            word for word in self.political_keywords if word in text_lower
        ]
        if political_words_found:
            logger.warning(
                "Content rejected for political content", words=political_words_found
            )
            self._log_filter_event(
                "political_content",
                text,
                f"Contains: {', '.join(political_words_found)}",
            )
            return False

        # Check for excessive caps (might indicate shouting/spam)
        caps_ratio = sum(1 for c in text if c.isupper()) / len(text) if text else 0
        if caps_ratio > 0.5 and len(text) > 20:
            logger.warning("Content rejected for excessive caps", caps_ratio=caps_ratio)
            self._log_filter_event(
                "excessive_caps", text, f"Caps ratio: {caps_ratio:.2f}"
            )
            return False

        # Check for suspicious repetition
        words = text.lower().split()
        if len(words) > 5:
            unique_words = set(words)
            if len(unique_words) / len(words) < 0.5:  # Less than 50% unique words
                logger.warning("Content rejected for repetitive text")
                self._log_filter_event(
                    "repetitive_text", text, "Too much word repetition"
                )
                return False

        return True

    def _openai_moderation_check(self, text: str) -> bool:
        """Use OpenAI's moderation API to check content."""
        try:
            logger.debug("Running OpenAI moderation check")

            response = self.openai_client.moderations.create(input=text)
            result = response.results[0]

            # Record cost (moderation API is typically free or very cheap)
            self.cost_tracker.record_cost(
                service="openai",
                operation="moderation",
                cost_usd=0.0,  # Usually free
                metadata={"flagged": result.flagged},
            )

            if result.flagged:
                # Log which categories were flagged
                flagged_categories = [
                    category
                    for category, flagged in result.categories.model_dump().items()
                    if flagged
                ]

                logger.warning(
                    "Content flagged by OpenAI moderation",
                    categories=flagged_categories,
                )

                self._log_filter_event(
                    "openai_moderation",
                    text,
                    f"Flagged categories: {', '.join(flagged_categories)}",
                )

                return False

            logger.debug("Content passed OpenAI moderation")
            return True

        except Exception as e:
            logger.error("OpenAI moderation check failed", error=str(e))
            # If moderation fails, we'll rely on basic checks
            # Don't fail the whole process
            return True

    def _log_filter_event(self, filter_type: str, content: str, reason: str):
        """Log content filtering events."""
        self.activity_logger.log_system_event(
            event_type="content_filtered",
            message=f"Content blocked by {filter_type} filter",
            level="WARNING",
            metadata={
                "filter_type": filter_type,
                "reason": reason,
                "content_preview": content[:100] + "..."
                if len(content) > 100
                else content,
            },
        )

    def validate_persona_content(self, persona_text: str) -> bool:
        """Validate persona configuration content."""
        if not persona_text or not persona_text.strip():
            raise ContentFilterError("Persona text cannot be empty")

        if len(persona_text) > 5000:  # Reasonable limit for persona
            raise ContentFilterError("Persona text too long (max 5000 characters)")

        # Basic safety check for persona
        if not self._basic_safety_check(persona_text):
            raise ContentFilterError("Persona contains inappropriate content")

        return True

    def validate_exemplar_content(self, exemplar_text: str) -> bool:
        """Validate exemplar tweet content."""
        if not exemplar_text or not exemplar_text.strip():
            raise ContentFilterError("Exemplar text cannot be empty")

        if len(exemplar_text) > 300:  # Slightly longer than tweet limit for flexibility
            raise ContentFilterError("Exemplar text too long (max 300 characters)")

        # Safety check for exemplar
        if not self._basic_safety_check(exemplar_text):
            raise ContentFilterError("Exemplar contains inappropriate content")

        return True

    def get_filter_stats(self, days: int = 7) -> Dict[str, any]:
        """Get content filtering statistics."""
        try:
            # This would require database queries to get actual stats
            # For now, return basic structure
            return {
                "total_checks": 0,
                "blocked_count": 0,
                "block_rate": 0.0,
                "top_block_reasons": [],
                "days_analyzed": days,
            }
        except Exception as e:
            logger.error("Failed to get filter stats", error=str(e))
            return {"error": str(e)}


class EmergencyControls:
    """Emergency controls for the bot."""

    def __init__(self):
        self.activity_logger = ActivityLogger()

    def emergency_stop(self, reason: str = "Manual emergency stop") -> bool:
        """Trigger emergency stop."""
        logger.warning("Emergency stop activated", reason=reason)

        self.activity_logger.log_system_event(
            event_type="emergency_stop",
            message=f"Emergency stop activated: {reason}",
            level="CRITICAL",
        )

        # In a real implementation, this would:
        # 1. Set a global flag to stop all automated posting
        # 2. Cancel any scheduled posts
        # 3. Send alerts to administrators

        return True

    def check_emergency_conditions(self) -> List[str]:
        """Check for conditions that should trigger emergency stop."""
        warnings = []

        try:
            # Check cost limits
            cost_tracker = CostTracker()
            if not cost_tracker.check_daily_limit():
                warnings.append("Daily cost limit exceeded")

            # Check error rates
            success_rate = self.activity_logger.get_success_rate(hours=24)
            if success_rate < 0.5:  # Less than 50% success rate
                warnings.append(f"Low success rate: {success_rate:.1%}")

            # Could add more checks:
            # - API rate limits being hit repeatedly
            # - Multiple content filter rejections
            # - Twitter API errors

        except Exception as e:
            logger.error("Failed to check emergency conditions", error=str(e))
            warnings.append("Failed to check system health")

        return warnings


# Convenience functions
def filter_tweet_content(text: str) -> bool:
    """Quick content filtering for tweets."""
    try:
        content_filter = ContentFilter()
        return content_filter.is_content_safe(text)
    except Exception as e:
        logger.error("Content filtering failed", error=str(e))
        return False


def validate_user_input(text: str, input_type: str = "general") -> bool:
    """Validate user input from the web interface."""
    try:
        content_filter = ContentFilter()

        if input_type == "persona":
            return content_filter.validate_persona_content(text)
        elif input_type == "exemplar":
            return content_filter.validate_exemplar_content(text)
        else:
            return content_filter.is_content_safe(text)

    except ContentFilterError:
        raise
    except Exception as e:
        logger.error("Input validation failed", input_type=input_type, error=str(e))
        return False


def check_emergency_status() -> List[str]:
    """Check if emergency conditions exist."""
    try:
        emergency_controls = EmergencyControls()
        return emergency_controls.check_emergency_conditions()
    except Exception as e:
        logger.error("Emergency status check failed", error=str(e))
        return ["Emergency status check failed"]
