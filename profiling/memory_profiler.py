import os
import time
import functools
import tracemalloc
from datetime import datetime
from flask import g, request
from loguru import logger

# Directory for storing profiling results
PROFILE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'profiling_results')
os.makedirs(PROFILE_DIR, exist_ok=True)

class MemoryProfiler:
    """
    Memory profiler for tracking memory usage of Python code.
    
    This class provides tools for profiling memory usage using tracemalloc.
    It can be used as a context manager or decorator to profile specific code blocks
    or functions.
    """
    
    def __init__(self, name=None, print_result=True, save_result=True, top_n=20):
        """
        Initialize the memory profiler.
        
        Args:
            name (str, optional): Name for this profiling session. If None, a timestamp will be used.
            print_result (bool): Whether to print profiling results to console.
            save_result (bool): Whether to save profiling results to file.
            top_n (int): Number of top memory allocations to display.
        """
        self.name = name or f"memory_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.print_result = print_result
        self.save_result = save_result
        self.top_n = top_n
        
    def __enter__(self):
        """Start memory tracking when entering context."""
        tracemalloc.start()
        self.start_time = time.time()
        self.start_snapshot = tracemalloc.take_snapshot()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop memory tracking when exiting context and process results."""
        end_snapshot = tracemalloc.take_snapshot()
        duration = time.time() - self.start_time
        
        # Compare with start snapshot
        stats = end_snapshot.compare_to(self.start_snapshot, 'lineno')
        
        # Format results
        result = []
        result.append(f"Memory profiling results for '{self.name}' (took {duration:.2f}s):")
        result.append(f"Top {self.top_n} memory allocations:")
        
        for stat in stats[:self.top_n]:
            result.append(f"{stat.size_diff / 1024:.1f} KB: {stat.traceback.format()[0]}")
        
        result_str = "\n".join(result)
        
        if self.print_result:
            logger.info(result_str)
            
        if self.save_result:
            # Save to file
            filename = os.path.join(PROFILE_DIR, f"{self.name}_memory.txt")
            with open(filename, 'w') as f:
                f.write(result_str)
                f.write("\n\nDetailed allocations:\n")
                for stat in stats[:50]:  # Save more details to file
                    f.write(f"{stat.size_diff / 1024:.1f} KB: {stat.traceback.format()[0]}\n")
                    for line in stat.traceback.format()[1:]:
                        f.write(f"    {line}\n")
            
            logger.info(f"Memory profiling data saved to {filename}")
            
        tracemalloc.stop()
        return False  # Don't suppress exceptions
        
    @classmethod
    def profile(cls, func=None, **kwargs):
        """
        Decorator for profiling memory usage of a function.
        
        Args:
            func: The function to profile
            **kwargs: Additional arguments to pass to the MemoryProfiler constructor
            
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


def profile_request_memory():
    """
    Profile memory usage for the current Flask request.
    
    This function should be called at the beginning of a request to start memory profiling.
    It will automatically save the profiling results when the request completes.
    """
    # Generate a unique name for this request
    endpoint = request.endpoint or 'unknown'
    request_id = getattr(g, 'request_id', 'unknown')
    name = f"request_memory_{endpoint}_{request_id}"
    
    # Create and start profiler
    profiler = MemoryProfiler(name=name, print_result=False)
    profiler.__enter__()
    
    # Store profiler in g for later access
    g.memory_profiler = profiler
    
    return profiler
    
def end_request_memory_profiling():
    """End request memory profiling and save results."""
    if hasattr(g, 'memory_profiler'):
        g.memory_profiler.__exit__(None, None, None)