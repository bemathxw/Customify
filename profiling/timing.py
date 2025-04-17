import time
import functools
from flask import g, request
from loguru import logger

class Timer:
    """
    Timer utility for measuring execution time of code blocks.
    
    This class provides a simple way to measure how long a piece of code takes to execute.
    It can be used as a context manager or decorator.
    """
    
    def __init__(self, name=None, log_level='INFO'):
        """
        Initialize the timer.
        
        Args:
            name (str, optional): Name for this timing session. Used in log messages.
            log_level (str): Log level to use for timing messages.
        """
        self.name = name or 'Timer'
        self.log_level = log_level.lower()
        self.start_time = None
        self.log_func = getattr(logger, self.log_level)
        
    def __enter__(self):
        """Start the timer when entering context."""
        self.start_time = time.time()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Log the elapsed time when exiting context."""
        elapsed = time.time() - self.start_time
        self.log_func(f"{self.name} took {elapsed:.4f} seconds")
        return False  # Don't suppress exceptions
        
    def elapsed(self):
        """Return the elapsed time in seconds."""
        if self.start_time is None:
            return 0
        return time.time() - self.start_time
        
    @classmethod
    def time(cls, func=None, **kwargs):
        """
        Decorator for timing a function.
        
        Args:
            func: The function to time
            **kwargs: Additional arguments to pass to the Timer constructor
            
        Returns:
            Decorated function
        """
        def decorator(f):
            @functools.wraps(f)
            def wrapper(*args, **kwargs):
                name = kwargs.pop('timer_name', f.__name__)
                with cls(name=name, **kwargs):
                    return f(*args, **kwargs)
            return wrapper
            
        if func:
            return decorator(func)
        return decorator


# Dictionary to store timing metrics
_timing_metrics = {}

def record_timing(name, duration):
    """
    Record a timing metric.
    
    Args:
        name (str): Name of the metric
        duration (float): Duration in seconds
    """
    if name not in _timing_metrics:
        _timing_metrics[name] = {
            'count': 0,
            'total_time': 0,
            'min_time': float('inf'),
            'max_time': 0
        }
        
    _timing_metrics[name]['count'] += 1
    _timing_metrics[name]['total_time'] += duration
    _timing_metrics[name]['min_time'] = min(_timing_metrics[name]['min_time'], duration)
    _timing_metrics[name]['max_time'] = max(_timing_metrics[name]['max_time'], duration)
    
def get_timing_metrics():
    """
    Get all recorded timing metrics.
    
    Returns:
        dict: Dictionary of timing metrics with calculated averages
    """
    result = {}
    for name, data in _timing_metrics.items():
        result[name] = {
            'count': data['count'],
            'total_time': data['total_time'],
            'avg_time': data['total_time'] / data['count'] if data['count'] > 0 else 0,
            'min_time': data['min_time'] if data['min_time'] != float('inf') else 0,
            'max_time': data['max_time']
        }
    return result
    
def reset_timing_metrics():
    """Reset all timing metrics."""
    global _timing_metrics
    _timing_metrics = {}


def timed(name=None, log_level='INFO'):
    """
    Decorator for timing a function and recording metrics.
    
    Args:
        name (str, optional): Name for the timing metric. Defaults to function name.
        log_level (str): Log level to use for timing messages.
        
    Returns:
        Decorated function
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            metric_name = name or func.__name__
            start_time = time.time()
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            
            # Log the timing
            log_func = getattr(logger, log_level.lower())
            log_func(f"{metric_name} took {duration:.4f} seconds")
            
            # Record the metric
            record_timing(metric_name, duration)
            
            return result
        return wrapper
    return decorator