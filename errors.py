import uuid
from datetime import datetime
from functools import wraps
import sys
import traceback

from loguru import logger

class AppError(Exception):
    """Base exception class for application errors with context tracking."""
    
    def __init__(self, message, error_code="APP_ERROR", context=None):
        """
        Initialize application error with message, code and context.
        
        Args:
            message (str): Human-readable error description
            error_code (str, optional): Error code for categorization
            context (dict, optional): Additional context data about the error
        """
        self.message = message
        self.error_code = error_code
        self.error_id = str(uuid.uuid4())
        self.timestamp = datetime.now().isoformat()
        self.context = context or {}
        super().__init__(message)
    
    def to_dict(self):
        """Convert error to dictionary for logging or API responses."""
        return {
            "error_id": self.error_id,
            "timestamp": self.timestamp,
            "error_code": self.error_code,
            "message": self.message,
            "context": self.context
        }
    
    def log(self, level="ERROR"):
        """Log the error with appropriate level and context."""
        log_method = getattr(logger, level.lower())
        log_method(f"[{self.error_id}] {self.error_code}: {self.message}", context=self.context)
        return self

class SpotifyAPIError(AppError):
    """Error related to Spotify API operations."""
    def __init__(self, message, status_code=None, endpoint=None, context=None):
        context = context or {}
        context.update({
            "spotify_endpoint": endpoint,
            "status_code": status_code
        })
        super().__init__(message, error_code="SPOTIFY_API_ERROR", context=context)

class AuthenticationError(AppError):
    """Error related to authentication processes."""
    def __init__(self, message, context=None):
        super().__init__(message, error_code="AUTH_ERROR", context=context)

class DataProcessingError(AppError):
    """Error related to data processing operations."""
    def __init__(self, message, data_type=None, context=None):
        context = context or {}
        context.update({"data_type": data_type})
        super().__init__(message, error_code="DATA_PROCESSING_ERROR", context=context)

def catch_exceptions(func):
    """
    Decorator to catch and handle exceptions in functions.
    
    This decorator wraps a function to catch any exceptions it raises,
    log them with a unique ID, and re-raise them as AppError instances
    if they aren't already.
    
    Args:
        func: The function to decorate
        
    Returns:
        The decorated function
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except AppError:
            # Re-raise AppError instances as they're already formatted properly
            raise
        except Exception as e:
            # For other exceptions, log them and convert to AppError
            error_id = str(uuid.uuid4())
            
            # Get stack trace
            exc_type, exc_value, exc_traceback = sys.exc_info()
            stack_trace = traceback.format_exception(exc_type, exc_value, exc_traceback)
            
            # Log the error
            logger.error(
                f"[{error_id}] Exception in {func.__name__}: {str(e)}",
                exc_info=True
            )
            
            # Convert to AppError and raise
            raise AppError(
                f"An error occurred in {func.__name__}: {str(e)}",
                error_code="FUNCTION_ERROR",
                context={
                    "function": func.__name__,
                    "module": func.__module__,
                    "error_id": error_id,
                    "original_error": str(e),
                    "stack_trace": stack_trace
                }
            )
    
    # Не пытаемся добавлять атрибуты к функции
    return wrapper

# Утилитарная функция для безопасного выполнения кода
def safe_execute(func, *args, default=None, **kwargs):
    """
    Safely execute a function with exception handling.
    
    Args:
        func: Function to execute
        *args: Arguments to pass to the function
        default: Default value to return if function raises an exception
        **kwargs: Keyword arguments to pass to the function
        
    Returns:
        Function result or default value if an exception occurs
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        error_id = str(uuid.uuid4())
        logger.error(
            f"[{error_id}] Error executing {func.__name__}: {str(e)}",
            exc_info=True
        )
        return default 