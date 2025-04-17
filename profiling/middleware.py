from flask import request, g
import time
import os
from loguru import logger

from .cpu_profiler import profile_request, end_request_profiling
from .memory_profiler import profile_request_memory, end_request_memory_profiling
from .timing import record_timing

# Configuration
PROFILE_REQUESTS = os.environ.get('PROFILE_REQUESTS', 'false').lower() == 'true'
PROFILE_MEMORY = os.environ.get('PROFILE_MEMORY', 'false').lower() == 'true'
PROFILE_THRESHOLD = float(os.environ.get('PROFILE_THRESHOLD', '1.0'))  # seconds

def init_profiling_middleware(app):
    """
    Initialize profiling middleware for Flask application.
    
    This function sets up request hooks to profile requests that exceed
    a certain threshold.
    
    Args:
        app: Flask application instance
    """
    @app.before_request
    def before_request_profiling():
        """Start profiling for the current request if enabled."""
        g.start_time = time.time()
        
        # Only profile certain endpoints
        if should_profile_request():
            if PROFILE_REQUESTS:
                profile_request()
            if PROFILE_MEMORY:
                profile_request_memory()
    
    @app.after_request
    def after_request_profiling(response):
        """End profiling and record metrics for the current request."""
        if hasattr(g, 'start_time'):
            duration = time.time() - g.start_time
            endpoint = request.endpoint or 'unknown'
            
            # Record timing for all requests
            record_timing(f"request.{endpoint}", duration)
            
            # Log slow requests
            if duration > PROFILE_THRESHOLD:
                logger.warning(f"Slow request: {request.method} {request.path} took {duration:.2f}s")
                
                # If we haven't already profiled this request but it's slow, profile it now
                if not hasattr(g, 'cpu_profiler') and PROFILE_REQUESTS:
                    logger.info(f"Profiling slow request: {request.method} {request.path}")
                    profile_request()
                    end_request_profiling()
            
            # End profiling if it was started
            if hasattr(g, 'cpu_profiler'):
                end_request_profiling()
            if hasattr(g, 'memory_profiler'):
                end_request_memory_profiling()
                
        return response
    
    logger.info("Profiling middleware initialized")
    logger.info(f"Request profiling: {'enabled' if PROFILE_REQUESTS else 'disabled'}")
    logger.info(f"Memory profiling: {'enabled' if PROFILE_MEMORY else 'disabled'}")
    logger.info(f"Profiling threshold: {PROFILE_THRESHOLD}s")
    
    return app

def should_profile_request():
    """
    Determine if the current request should be profiled.
    
    Returns:
        bool: True if the request should be profiled, False otherwise
    """
    # Skip static files
    if request.path.startswith('/static/'):
        return False
        
    # Skip health checks or other frequent endpoints
    if request.path == '/health' or request.path == '/ping':
        return False
        
    # Profile API endpoints and specific views
    if request.path.startswith('/api/') or request.path == '/profile':
        return True
        
    # Default to not profiling
    return False