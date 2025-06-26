"""
Custom exception hierarchy - Structured error handling system.

This module defines a comprehensive exception hierarchy that enables
precise error handling throughout the application. Each exception type
corresponds to a specific failure mode, allowing for targeted recovery
strategies and meaningful error messages.

Exception Hierarchy:
- ZenKinkBotException: Base for all application errors
  - ConfigurationError: Missing/invalid configuration
  - APIError: External API failures
    - OpenAIError: OpenAI API issues
    - TwitterError: Twitter API issues
  - ContentFilterError: Content safety violations
  - CostLimitError: Budget exceeded
  - VectorDBError: Database operations
  - GenerationError: Tweet generation failures

Usage enables specific error handling:
    try:
        post_tweet()
    except TwitterError:
        # Handle Twitter-specific issues
    except CostLimitError:
        # Trigger emergency stop
    except ZenKinkBotException:
        # Handle any bot error
"""


class ZenKinkBotException(Exception):
    """Base exception for all bot-related errors."""

    pass


class ConfigurationError(ZenKinkBotException):
    """Raised when there's an issue with configuration."""

    pass


class APIError(ZenKinkBotException):
    """Base class for API-related errors."""

    pass


class OpenAIError(APIError):
    """Raised when OpenAI API calls fail."""

    pass


class TwitterError(APIError):
    """Raised when Twitter API calls fail."""

    pass


class ContentFilterError(ZenKinkBotException):
    """Raised when content fails filtering checks."""

    pass


class CostLimitError(ZenKinkBotException):
    """Raised when cost limits are exceeded."""

    pass


class VectorDBError(ZenKinkBotException):
    """Raised when vector database operations fail."""

    pass


class GenerationError(ZenKinkBotException):
    """Raised when tweet generation fails."""

    pass
