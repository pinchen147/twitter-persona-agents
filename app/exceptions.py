"""Custom exception classes for the Zen Kink Bot."""

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