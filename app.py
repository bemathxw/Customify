import os
import time
import uuid
import traceback
from datetime import datetime, timedelta
import sys
from functools import wraps
import logging

from dotenv import load_dotenv
from flask import Flask, flash, g, jsonify, render_template, request, session, redirect, url_for
from loguru import logger
from flask_session import Session

# COMPLETE DISABLING OF LOGGING FOR NOW-PLAYING REQUESTS
# ===================================================

# 1. Disable Flask logs
from flask.logging import default_handler
default_handler.setLevel(logging.ERROR)  # Set high logging level for Flask

# 2. Intercept all standard Python logs
class NowPlayingFilter(logging.Filter):
    def filter(self, record):
        # If this line contains now-playing, filter it
        if hasattr(record, 'msg') and isinstance(record.msg, str) and 'now-playing' in record.msg:
            return False
        
        # Check args if they exist
        if hasattr(record, 'args'):
            args_str = str(record.args)
            if 'now-playing' in args_str:
                return False
                
        return True

# Apply filter to Python's root logger
root_logger = logging.getLogger()
root_logger.addFilter(NowPlayingFilter())

# 3. Disable Werkzeug logs
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.setLevel(logging.ERROR)  # Only critical errors
werkzeug_logger.addFilter(NowPlayingFilter())

# 4. Patch WSGIRequestHandler to ignore now-playing
from werkzeug.serving import WSGIRequestHandler

original_log = WSGIRequestHandler.log

def silent_log(self, type, message, *args):
    if 'now-playing' not in message:
        original_log(self, type, message, *args)

WSGIRequestHandler.log = silent_log

# 5. Global variable for tracking now-playing requests
class RequestState:
    is_now_playing = False

req_state = RequestState()

# Other imports
from errors import AppError, SpotifyAPIError, AuthenticationError, DataProcessingError, catch_exceptions, safe_execute
from spotify_api import get_recommendations, get_top_tracks, is_premium_user, get_headers, get_current_user, get_spotify_user_profile
from spotify import spotify_bp
import jinja2

# Import profiling system
from profiling import (
    init_profiling_middleware, timed, CPUProfiler, MemoryProfiler,
    get_timing_metrics, APIProfiler, start_resource_monitoring,
    stop_resource_monitoring, get_resource_metrics_summary,
    get_user_metrics
)

# Configure Flask to disable logging for now-playing requests
class CustomFlask(Flask):
    def log_request(self, response):
        # Override log_request method to filter now-playing requests
        if not request.path.endswith('/now-playing'):
            super().log_request(response)

# Filter to exclude now-playing requests from logs
def filter_now_playing(record):
    """
    Pass logs for all requests except requests to /spotify/now-playing
    """
    # Check if the message or request path contains now-playing
    if "now-playing" in record["message"].lower():
        return False
    
    # Check extra data if it exists
    if "extra" in record and record["extra"]:
        path = record["extra"].get("path", "")
        if isinstance(path, str) and "now-playing" in path:
            return False
            
    return True

# Enhanced logging setup
def setup_logging():
    """
    Configure application logging based on environment variables using Loguru.
    
    Log levels can be set using the LOG_LEVEL environment variable:
    - DEBUG: Detailed information, typically useful for debugging
    - INFO: Confirmation that things are working as expected
    - WARNING: Indication that something unexpected happened
    - ERROR: Something failed but the application can continue
    - CRITICAL: A serious error that may prevent the application from continuing
    
    If LOG_LEVEL is not set, it defaults to INFO.
    """
    # Get log level from environment variable or default to INFO
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # Remove default logger
    logger.remove()
    
    # Custom filter for Loguru
    def advanced_filter(record):
        """Advanced filter for Loguru"""
        # Check global request state
        if req_state.is_now_playing:
            return False
            
        # Check message
        if "now-playing" in record["message"].lower():
            return False
            
        # Check additional data
        extra = record.get("extra", {})
        if extra and isinstance(extra, dict):
            # Check request path if exists
            path = extra.get("path", "")
            if isinstance(path, str) and "now-playing" in path:
                return False
                
        return True
    
    # Add console logger with filter
    logger.add(
        sys.stdout,
        level=log_level,
        filter=advanced_filter,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    
    # Create logs directory structure if it doesn't exist
    os.makedirs("logs/app", exist_ok=True)
    os.makedirs("logs/access", exist_ok=True)
    os.makedirs("logs/error", exist_ok=True)
    os.makedirs("logs/performance", exist_ok=True)
    
    # 1. Main application logs (INFO and above)
    logger.add(
        "logs/app/app_{time:YYYY-MM-DD}.log",
        rotation="00:00",  # Rotate at midnight
        retention="30 days",  # Keep logs for 30 days
        compression="zip",  # Compress rotated logs
        level="INFO",
        filter=filter_now_playing,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{line} - {message}"
    )
    
    # 2. Debug logs (all levels)
    logger.add(
        "logs/app/debug_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="7 days",
        compression="zip",
        level="DEBUG",
        filter=filter_now_playing,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{line} - {message}"
    )
    
    # 3. Access logs (for requests)
    logger.add(
        "logs/access/access_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        compression="zip",
        filter=lambda record: record["function"] == "log_request_info" and filter_now_playing(record),
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}"
    )
    
    # 4. Error logs (WARNING and above)
    logger.add(
        "logs/error/error_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="60 days",
        compression="zip",
        level="WARNING",
        filter=filter_now_playing,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{line} - {message}"
    )
    
    # 5. Performance logs
    logger.add(
        "logs/performance/perf_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        compression="zip",
        filter=lambda record: "Performance:" in record["message"] and filter_now_playing(record),
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}"
    )
    
    logger.info("Logging setup complete with level: {}", log_level)

# Call setup_logging at module level
setup_logging()

# Load environment variables
load_dotenv()

# Initialize Flask app
app = CustomFlask(__name__, template_folder="templates")
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_key_for_testing')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# Debug output to check environment variables
logger.debug(f"SPOTIFY_CLIENT_ID: {os.getenv('SPOTIFY_CLIENT_ID')}")
logger.debug(f"SPOTIFY_CLIENT_SECRET: {os.getenv('SPOTIFY_CLIENT_SECRET')}")

logger.info("Initializing Flask application")

# Register Spotify blueprint
app.register_blueprint(spotify_bp, url_prefix="/spotify")
logger.info("Registered Spotify blueprint")

# Initialize profiling middleware
init_profiling_middleware(app)

# Enhanced context for logging
class ContextualLogger:
    """
    Middleware to add contextual information to all log records.
    
    This class adds user, session, and request information to all log records
    automatically, without needing to specify it in each log call.
    """
    
    @staticmethod
    def add_context_to_record(record):
        """
        Add contextual information to a log record.
        
        Args:
            record (dict): The log record to enhance
        """
        # Add request information if available
        if request:
            record["extra"].update({
                "request_id": getattr(g, 'request_id', 'no_request_id'),
                "ip": request.remote_addr,
                "method": request.method,
                "path": request.path,
                "user_agent": request.user_agent.string if hasattr(request, 'user_agent') else "Unknown"
            })
            
            # Add user information if available
            if 'user_id' in session:
                record["extra"].update({
                    "user_id": session.get('user_id'),
                    "username": session.get('username', 'unknown')
                })
            
            # Add session information
            if session:
                # Don't log sensitive session data, just keys
                record["extra"].update({
                    "session_keys": list(session.keys())
                })
        
        return record

# Configure Loguru to use the context processor
logger.configure(patcher=ContextualLogger.add_context_to_record)

# Performance monitoring
class PerformanceLogger:
    """
    Context manager for logging the execution time of code blocks.
    
    Usage:
        with PerformanceLogger("Operation name"):
            # code to measure
    """
    
    def __init__(self, operation_name):
        self.operation_name = operation_name
        
    @catch_exceptions
    def __enter__(self):
        self.start_time = time.time()
        return self
        
    @catch_exceptions
    def __exit__(self, exc_type, exc_val, exc_tb):
        end_time = time.time()
        duration = end_time - self.start_time
        if duration > 1.0:  # Log only if operation takes more than 1 second
            logger.warning(f"Performance: {self.operation_name} took {duration:.2f} seconds")
        else:
            logger.debug(f"Performance: {self.operation_name} took {duration:.2f} seconds")
        
        if exc_type:
            logger.error(f"Exception in {self.operation_name}: {exc_val}", exc_info=True)

# Apply decorator to all Spotify API functions
def apply_exception_handling(module):
    """
    Apply exception handling to all functions in a module.
    
    This function wraps all callable objects in the module with the
    catch_exceptions decorator, unless they are already decorated
    or are Flask view functions.
    
    Args:
        module: The module to apply exception handling to
    """
    for name in dir(module):
        if name.startswith('__'):
            continue
            
        try:
            attr = getattr(module, name)
            
            # Skip if not callable
            if not callable(attr):
                continue
                
            # Skip if already decorated
            if hasattr(attr, '__wrapped__'):
                continue
                
            # Skip Flask view functions (check multiple attributes)
            if hasattr(attr, 'view_class') or hasattr(attr, '_is_view') or hasattr(attr, '__blueprints__'):
                continue
                
            # Check if function is a Flask route
            if hasattr(attr, '__module__') and 'flask' in attr.__module__:
                continue
                
            # Additional check for Blueprint routes
            if name in getattr(module, 'view_functions', {}) or hasattr(attr, 'methods'):
                continue
                
            # Apply decorator
            logger.debug(f"Applying exception handling to {module.__name__}.{name}")
            setattr(module, name, catch_exceptions(attr))
        except Exception as e:
            logger.warning(f"Failed to apply exception handling to {module.__name__}.{name}: {str(e)}")

# Override Flask's route decorator to mark view functions
original_route = app.route
def route_wrapper(*args, **kwargs):
    def decorator(f):
        view_func = original_route(*args, **kwargs)(f)
        view_func._is_view = True
        return view_func
    return decorator
app.route = route_wrapper

# Request logging
@app.before_request
def log_request_info():
    """
    Log information about each incoming request.
    
    This function runs before each request is processed. It logs the request method,
    path, client IP address, and optionally headers and form/JSON data for debugging.
    """
    logger.info(f"Request: {request.method} {request.path} from {request.remote_addr}")
    logger.debug(f"Headers: {request.headers}")
    if request.method == "POST":
        logger.debug(f"Form data: {request.form}")
        logger.debug(f"JSON data: {request.get_json(silent=True)}")

# Middleware to set request context
@app.before_request
def before_request():
    """Set up request context for logging and tracking"""
    g.request_id = str(uuid.uuid4())
    g.start_time = time.time()
    
    # Extract user ID from Spotify profile if available
    if 'spotify_token' in session and 'user_id' not in session:
        try:
            headers = get_headers()
            if headers:
                user_data = get_current_user(headers)
                if user_data and 'id' in user_data:
                    session['user_id'] = user_data['id']
                    session['username'] = user_data.get('display_name', user_data['id'])
        except Exception as e:
            logger.warning(f"Failed to get user data for context: {str(e)}")
    
    # Log the beginning of request processing with context
    logger.info(f"Processing request: {request.method} {request.path}")

@app.after_request
def after_request(response):
    """Log request completion and timing"""
    if hasattr(g, 'request_id') and hasattr(g, 'start_time'):
        duration = time.time() - g.start_time
        logger.info(
            f"Request {g.request_id} completed in {duration:.2f}s with status {response.status_code}"
        )
    return response

@app.teardown_request
def teardown_request(exception):
    """Ensure exceptions during request teardown are logged"""
    if exception:
        error_id = str(uuid.uuid4())
        logger.error(
            f"[{error_id}] Exception during request teardown: {str(exception)}",
            exc_info=True
        )

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors."""
    error_id = str(uuid.uuid4())
    logger.warning(f"[{error_id}] 404 error: {request.path} accessed by {request.remote_addr}")
    
    try:
        return render_template('404.html', error_id=error_id), 404
    except jinja2.exceptions.TemplateNotFound:
        # Fallback if 404.html is not found
        try:
            # Try to use error.html as fallback
            return render_template('error.html', 
                error={
                    "error_id": error_id,
                    "message": "The page you are looking for does not exist or has been moved.",
                    "error_code": "404",
                    "timestamp": datetime.now().isoformat()
                }
            ), 404
        except jinja2.exceptions.TemplateNotFound:
            # Last resort - plain HTML
            return f"""
            <html>
                <head><title>Page Not Found</title></head>
                <body>
                    <h1>404 - Page Not Found</h1>
                    <p>The page you are looking for does not exist or has been moved.</p>
                    <p>Error ID: {error_id}</p>
                    <p><a href="/">Go to Home Page</a></p>
                </body>
            </html>
            """, 404

@app.errorhandler(500)
def internal_server_error(e):
    """Handle 500 errors and log them with unique ID."""
    error_id = str(uuid.uuid4())
    logger.error(
        f"[{error_id}] 500 error: {str(e)}",
        exc_info=True,
        context={"url": request.path, "method": request.method, "ip": request.remote_addr}
    )
    return render_template('500.html', error_id=error_id), 500

@app.errorhandler(Exception)
def handle_all_exceptions(e):
    """Handle all unhandled exceptions."""
    error_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()
    
    # Log the exception
    logger.error(
        f"[{error_id}] Unhandled exception: {str(e)}",
        exc_info=True
    )
    
    # Try to render error template, fallback to simple text response if template not found
    try:
        return render_template(
            'error.html',
            error={
                "error_id": error_id,
                "message": "An unexpected error occurred. Please try again later.",
                "timestamp": timestamp,
                "error_code": "INTERNAL_SERVER_ERROR"
            }
        ), 500
    except jinja2.exceptions.TemplateNotFound:
        # Fallback if error template is not found
        return f"""
        <html>
            <head><title>Server Error</title></head>
            <body>
                <h1>500 - Internal Server Error</h1>
                <p>An unexpected error occurred. Please try again later.</p>
                <p>Error ID: {error_id}</p>
                <p>Time: {timestamp}</p>
                <p><a href="/">Go to Home Page</a></p>
            </body>
        </html>
        """, 500

# Helper function to handle exceptions in routes
def handle_exception(e):
    """
    Handle exceptions in route handlers.
    
    This function provides consistent error handling for all routes.
    It logs the exception, formats an appropriate response, and returns
    it to the client.
    
    Args:
        e: The exception to handle
        
    Returns:
        Flask response with appropriate error information
    """
    # If this is an AppError, use its information
    if isinstance(e, AppError):
        error_id = e.error_id
        error_code = e.error_code
        message = e.message
        timestamp = e.timestamp
        context = e.context
        
        # Log the error
        logger.error(
            f"[{error_id}] {error_code}: {message}",
            context=context
        )
    else:
        # For other exceptions, generate new error information
        error_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        message = str(e)
        
        # Get stack trace
        exc_type, exc_value, exc_traceback = sys.exc_info()
        stack_trace = traceback.format_exception(exc_type, exc_value, exc_traceback)
        
        # Log the error
        logger.error(
            f"[{error_id}] Unhandled exception: {message}",
            exc_info=True
        )
    
    # For API endpoints, return JSON response
    if request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
        return jsonify({
            "error": True,
            "error_id": error_id,
            "message": message,
            "timestamp": timestamp
        }), 500
    
    # For web pages, render error template
    error_data = {
        "error_id": error_id,
        "message": message,
        "timestamp": timestamp,
        "error_code": error_code if isinstance(e, AppError) else "UNKNOWN_ERROR"
    }
    
    return render_template('error.html', error=error_data), 500

# Routes
@app.route('/')
def home():
    """Render the home page."""
    logger.info("Rendering home page")
    logger.debug(f"Session in home: {session}")
    
    # Check if user is authenticated
    if 'spotify_token' in session:
        logger.info(f"User is authenticated: {session.get('username', 'Unknown')}")
    else:
        logger.info("User is not authenticated")
    
    return render_template('home.html')

@app.route('/api/recommendations', methods=['GET'])
def api_recommendations():
    """Endpoint for getting recommendations"""
    try:
        app.logger.info("Requesting recommendations")
        
        # Check authorization
        if 'spotify_token' not in session:
            app.logger.warning("User not authorized to get recommendations")
            return jsonify({
                'success': False,
                'error': 'Spotify authorization required'
            }), 401
        
        # Get recommendations
        result = get_recommendations()
        
        # Return result
        if not result.get('success'):
            app.logger.error(f"Error getting recommendations: {result.get('error')}")
            return jsonify(result), 500
        
        return jsonify(result)
        
    except Exception as e:
        app.logger.error(f"Unexpected error when getting recommendations: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f"Internal server error: {str(e)}"
        }), 500

@app.route('/profile')
def profile():
    """Render the user profile page."""
    logger.info("Rendering profile page")
    logger.debug(f"Session in profile: {session}")
    
    # Check if user is authenticated
    if 'spotify_token' not in session:
        logger.info("User not authenticated, showing login button")
        return render_template('profile.html', show_login_button=True)
    
    # Get user's top tracks
    try:
        headers = get_headers()
        if not headers:
            logger.warning("Failed to get valid headers, showing login button")
            return render_template('profile.html', show_login_button=True)
        
        user_data = get_spotify_user_profile()
        # Get top tracks
        top_tracks = get_top_tracks(headers)
        
        # Check if user is a premium user
        premium_user = is_premium_user()
        
        logger.info(f"Rendering profile with {len(top_tracks)} top tracks")
        return render_template(
            'profile.html', 
            show_login_button=False, 
            top_tracks=top_tracks,
            user_name=user_data.get('display_name', 'Spotify User'),
            user_avatar=user_data.get('images', [{}])[0].get('url') if user_data.get('images') else None,
            premium_user=premium_user
        )
    except Exception as e:
        logger.error(f"Error rendering profile: {str(e)}", exc_info=True)
        # In case of error, show page with login button
        return render_template('profile.html', show_login_button=True)

@app.route('/get-recommendations')
def get_recommendations_redirect():
    """
    Redirect to the API endpoint for recommendations.
    This route exists for backward compatibility.
    
    Returns:
        Redirect to /api/recommendations
    """
    logger.info("Redirecting from /get-recommendations to /api/recommendations")
    return redirect(url_for('api_recommendations'))

# Initialize the application with exception handling for all modules
def init_app():
    """Initialize the application with comprehensive exception handling"""
    # Set up uncaught exception hook for the entire process
    def handle_uncaught_exception(exc_type, exc_value, exc_traceback):
        """Handle uncaught exceptions at process level"""
        if issubclass(exc_type, KeyboardInterrupt):
            # Don't log keyboard interrupt (Ctrl+C)
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
            
        error_id = str(uuid.uuid4())
        logger.critical(
            f"[{error_id}] Uncaught exception at process level: {str(exc_value)}",
            exc_info=(exc_type, exc_value, exc_traceback)
        )
    
    # Replace the default exception hook
    sys.excepthook = handle_uncaught_exception
    
    logger.info("Application initialized with comprehensive exception handling")

# Instead of @app.before_first_request use with app.app_context()
# or create a function that will be called when the application starts

# Option 1: Using with app.app_context()
def init_app_resources():
    """Initialize application resources like monitoring."""
    start_resource_monitoring(interval=10.0, log_to_console=False)
    logger.info("Resource monitoring started")

# Call function when application starts
with app.app_context():
    init_app_resources()

# Option 2: Using first_request event
@app.before_request
def before_first_request_handler():
    """Start resource monitoring on first request."""
    if not hasattr(app, '_got_first_request'):
        app._got_first_request = True
        start_resource_monitoring(interval=10.0, log_to_console=False)
        logger.info("Resource monitoring started on first request")

# Add profiling dashboard route (admin only)
@app.route('/admin/profiling', methods=['GET'])
def profiling_dashboard():
    """
    Display profiling metrics dashboard.
    
    This route is for administrators only and shows performance metrics
    collected by the profiling tools.
    
    Returns:
        HTML page with profiling metrics
    """
    # In a real app, you would add authentication here
    # if not current_user.is_admin:
    #     return redirect(url_for('login'))
    
    # Get metrics
    timing_metrics = get_timing_metrics()
    api_metrics = APIProfiler.get_metrics()
    resource_metrics = get_resource_metrics_summary()
    user_metrics = get_user_metrics()
    
    return render_template(
        'admin/profiling.html',
        timing_metrics=timing_metrics,
        api_metrics=api_metrics,
        resource_metrics=resource_metrics,
        user_metrics=user_metrics
    )

# Add API endpoint for metrics (for monitoring tools)
@app.route('/api/metrics', methods=['GET'])
def api_metrics():
    """
    Return performance metrics as JSON.
    
    This endpoint is designed to be consumed by monitoring tools.
    
    Returns:
        JSON response with performance metrics
    """
    # In a real app, you would add authentication here
    # if 'api_key' not in request.args or request.args['api_key'] != API_KEY:
    #     return jsonify({"error": "Unauthorized"}), 401
    
    # Get metrics
    metrics = {
        'timing': get_timing_metrics(),
        'api': APIProfiler.get_metrics(),
        'resources': get_resource_metrics_summary()
    }
    
    return jsonify(metrics)


# Call initialization
if __name__ == "__main__":
    init_app()
    logger.info("Starting Flask application in debug mode")
    app.run(debug=True)

# Initialize session
Session(app)
