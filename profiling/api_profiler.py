import time
import functools
import json
import os
from datetime import datetime
from urllib.parse import urlparse
from loguru import logger
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# Directory for storing API profiling results
PROFILE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'profiling_results', 'api')
os.makedirs(PROFILE_DIR, exist_ok=True)

# Dictionary to store API metrics
_api_metrics = {}

class APIProfiler:
    """
    Profiler for monitoring and analyzing API requests.
    
    This class provides tools for tracking API request performance, including:
    - Request duration
    - Response size
    - Success/failure rates
    - Endpoint statistics
    """
    
    @staticmethod
    def record_api_call(endpoint, method, status_code, duration, response_size=0):
        """
        Record metrics for an API call.
        
        Args:
            endpoint (str): API endpoint that was called
            method (str): HTTP method used (GET, POST, etc.)
            status_code (int): HTTP status code returned
            duration (float): Request duration in seconds
            response_size (int): Size of response in bytes
        """
        # Parse domain from endpoint
        parsed_url = urlparse(endpoint)
        domain = parsed_url.netloc
        path = parsed_url.path
        
        # Create keys if they don't exist
        if domain not in _api_metrics:
            _api_metrics[domain] = {}
            
        if path not in _api_metrics[domain]:
            _api_metrics[domain][path] = {
                'count': 0,
                'success_count': 0,
                'error_count': 0,
                'total_time': 0,
                'min_time': float('inf'),
                'max_time': 0,
                'total_size': 0,
                'methods': {},
                'status_codes': {}
            }
            
        # Update metrics
        metrics = _api_metrics[domain][path]
        metrics['count'] += 1
        metrics['total_time'] += duration
        metrics['min_time'] = min(metrics['min_time'], duration)
        metrics['max_time'] = max(metrics['max_time'], duration)
        metrics['total_size'] += response_size
        
        # Track success/error counts
        if 200 <= status_code < 400:
            metrics['success_count'] += 1
        else:
            metrics['error_count'] += 1
            
        # Track methods
        if method not in metrics['methods']:
            metrics['methods'][method] = 0
        metrics['methods'][method] += 1
        
        # Track status codes
        if status_code not in metrics['status_codes']:
            metrics['status_codes'][status_code] = 0
        metrics['status_codes'][status_code] += 1
        
        # Log slow requests
        if duration > 1.0:  # Threshold for slow requests (1 second)
            logger.warning(f"Slow API call: {method} {endpoint} took {duration:.2f}s (status: {status_code})")
    
    @staticmethod
    def get_metrics():
        """
        Get all recorded API metrics with calculated averages.
        
        Returns:
            dict: Dictionary of API metrics by domain and endpoint
        """
        result = {}
        
        for domain, endpoints in _api_metrics.items():
            result[domain] = {}
            
            for path, data in endpoints.items():
                result[domain][path] = {
                    'count': data['count'],
                    'success_count': data['success_count'],
                    'error_count': data['error_count'],
                    'success_rate': data['success_count'] / data['count'] if data['count'] > 0 else 0,
                    'total_time': data['total_time'],
                    'avg_time': data['total_time'] / data['count'] if data['count'] > 0 else 0,
                    'min_time': data['min_time'] if data['min_time'] != float('inf') else 0,
                    'max_time': data['max_time'],
                    'total_size': data['total_size'],
                    'avg_size': data['total_size'] / data['count'] if data['count'] > 0 else 0,
                    'methods': data['methods'],
                    'status_codes': data['status_codes']
                }
                
        return result
    
    @staticmethod
    def reset_metrics():
        """Reset all API metrics."""
        global _api_metrics
        _api_metrics = {}
        
    @staticmethod
    def save_metrics_to_file():
        """Save current API metrics to a file."""
        metrics = APIProfiler.get_metrics()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = os.path.join(PROFILE_DIR, f"api_metrics_{timestamp}.json")
        
        with open(filename, 'w') as f:
            json.dump(metrics, f, indent=2)
            
        logger.info(f"API metrics saved to {filename}")
        return filename


class ProfiledSession(requests.Session):
    """
    A requests.Session subclass that automatically profiles all requests.
    
    This class wraps the standard requests.Session to add profiling capabilities
    to all HTTP requests made through it.
    """
    
    def __init__(self, timeout=10, retries=3, backoff_factor=0.3):
        """
        Initialize a profiled session with retry capabilities.
        
        Args:
            timeout (int): Default request timeout in seconds
            retries (int): Number of retries for failed requests
            backoff_factor (float): Backoff factor for retries
        """
        super().__init__()
        self.timeout = timeout
        
        # Set up retry strategy
        retry_strategy = Retry(
            total=retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.mount("http://", adapter)
        self.mount("https://", adapter)
        
    def request(self, method, url, **kwargs):
        """
        Override the request method to add profiling.
        
        Args:
            method (str): HTTP method
            url (str): Request URL
            **kwargs: Additional arguments for the request
            
        Returns:
            Response object
        """
        # Set default timeout if not provided
        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.timeout
            
        # Measure request time
        start_time = time.time()
        
        try:
            response = super().request(method, url, **kwargs)
            duration = time.time() - start_time
            
            # Get response size
            content_length = len(response.content) if response.content else 0
            
            # Record metrics
            APIProfiler.record_api_call(
                endpoint=url,
                method=method,
                status_code=response.status_code,
                duration=duration,
                response_size=content_length
            )
            
            return response
            
        except Exception as e:
            duration = time.time() - start_time
            
            # Record failed request
            APIProfiler.record_api_call(
                endpoint=url,
                method=method,
                status_code=0,  # Use 0 to indicate a failed request
                duration=duration
            )
            
            # Re-raise the exception
            raise


def profile_api_call(func=None, endpoint_name=None):
    """
    Decorator for profiling API calls.
    
    Args:
        func: The function to profile
        endpoint_name (str, optional): Custom name for the endpoint
        
    Returns:
        Decorated function
    """
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            # Get endpoint name
            name = endpoint_name or f.__name__
            
            # Measure request time
            start_time = time.time()
            
            try:
                result = f(*args, **kwargs)
                duration = time.time() - start_time
                
                # Determine status code and response size
                status_code = 200
                response_size = 0
                
                if hasattr(result, 'status_code'):
                    status_code = result.status_code
                    
                if hasattr(result, 'content'):
                    response_size = len(result.content) if result.content else 0
                elif isinstance(result, dict) or isinstance(result, list):
                    response_size = len(json.dumps(result))
                
                # Record metrics
                APIProfiler.record_api_call(
                    endpoint=name,
                    method='FUNC',  # Function call, not HTTP method
                    status_code=status_code,
                    duration=duration,
                    response_size=response_size
                )
                
                return result
                
            except Exception as e:
                duration = time.time() - start_time
                
                # Record failed request
                APIProfiler.record_api_call(
                    endpoint=name,
                    method='FUNC',
                    status_code=500,  # Use 500 to indicate an error
                    duration=duration
                )
                
                # Re-raise the exception
                raise
                
        return wrapper
        
    if func:
        return decorator(func)
    return decorator