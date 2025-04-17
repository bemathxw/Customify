import cProfile
import pstats
import io
import time
import functools
import os
from datetime import datetime
from flask import request, g
from loguru import logger

# Directory for storing profiling results
PROFILE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'profiling_results')
os.makedirs(PROFILE_DIR, exist_ok=True)

class CPUProfiler:
    """
    CPU profiler for measuring function execution time and resource usage.
    
    This class provides tools for profiling Python code execution using cProfile.
    It can be used as a context manager or decorator to profile specific code blocks
    or functions.
    """
    
    def __init__(self, name=None, print_result=True, save_result=True, sort_by='cumtime'):
        """
        Initialize the CPU profiler.
        
        Args:
            name (str, optional): Name for this profiling session. If None, a timestamp will be used.
            print_result (bool): Whether to print profiling results to console.
            save_result (bool): Whether to save profiling results to file.
            sort_by (str): Sorting criteria for profiling results. Options include:
                - 'cumtime': cumulative time
                - 'tottime': total time
                - 'calls': number of calls
                - 'pcalls': primitive calls
                - 'ncalls': call count
        """
        self.name = name or f"profile_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.print_result = print_result
        self.save_result = save_result
        self.sort_by = sort_by
        self.profiler = cProfile.Profile()
        
    def __enter__(self):
        """Start profiling when entering context."""
        self.start_time = time.time()
        self.profiler.enable()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop profiling when exiting context and process results."""
        self.profiler.disable()
        duration = time.time() - self.start_time
        
        # Process profiling results
        s = io.StringIO()
        ps = pstats.Stats(self.profiler, stream=s).sort_stats(self.sort_by)
        ps.print_stats(20)  # Print top 20 results
        
        if self.print_result:
            logger.info(f"Profiling results for '{self.name}' (took {duration:.2f}s):")
            logger.info(s.getvalue())
            
        if self.save_result:
            # Save to file
            filename = os.path.join(PROFILE_DIR, f"{self.name}.prof")
            self.profiler.dump_stats(filename)
            
            # Also save readable text version
            text_filename = os.path.join(PROFILE_DIR, f"{self.name}.txt")
            with open(text_filename, 'w') as f:
                stats = pstats.Stats(self.profiler, stream=f)
                stats.sort_stats(self.sort_by)
                stats.print_stats()
                
            logger.info(f"Profiling data saved to {filename} and {text_filename}")
            
        return False  # Don't suppress exceptions
        
    @classmethod
    def profile(cls, func=None, **kwargs):
        """
        Decorator for profiling a function.
        
        Args:
            func: The function to profile
            **kwargs: Additional arguments to pass to the CPUProfiler constructor
            
        Returns:
            Decorated function
        """
        def decorator(f):
            @functools.wraps(f)
            def wrapper(*args, **kwargs):
                name = kwargs.pop('profile_name', f.__name__)
                with cls(name=name, **kwargs):
                    return f(*args, **kwargs)
            return wrapper
            
        if func:
            return decorator(func)
        return decorator


def profile_request():
    """
    Profile the current Flask request.
    
    This function should be called at the beginning of a request to start profiling.
    It will automatically save the profiling results when the request completes.
    """
    # Generate a unique name for this request
    endpoint = request.endpoint or 'unknown'
    request_id = getattr(g, 'request_id', 'unknown')
    name = f"request_{endpoint}_{request_id}"
    
    # Create and start profiler
    profiler = CPUProfiler(name=name, print_result=False)
    profiler.__enter__()
    
    # Store profiler in g for later access
    g.cpu_profiler = profiler
    
    return profiler
    
def end_request_profiling():
    """End request profiling and save results."""
    if hasattr(g, 'cpu_profiler'):
        g.cpu_profiler.__exit__(None, None, None)