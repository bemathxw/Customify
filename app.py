import os
import time
import uuid
import traceback
from datetime import datetime, timedelta
import sys
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, flash, g, jsonify, render_template, request, session, redirect, url_for
from loguru import logger
from flask_session import Session

from errors import AppError, SpotifyAPIError, AuthenticationError, DataProcessingError, catch_exceptions, safe_execute
from spotify_api import get_recommendations, get_top_tracks, is_premium_user, get_headers, get_current_user
from spotify import spotify_bp
import jinja2

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
    
    # Create logs directory structure if it doesn't exist
    os.makedirs("logs/app", exist_ok=True)
    os.makedirs("logs/access", exist_ok=True)
    os.makedirs("logs/error", exist_ok=True)
    os.makedirs("logs/performance", exist_ok=True)
    
    # Add console logger
    logger.add(
        sys.stdout,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    
    # Add file loggers for different log types
    
    # 1. Main application logs (INFO and above)
    logger.add(
        "logs/app/app_{time:YYYY-MM-DD}.log",
        rotation="00:00",  # Rotate at midnight
        retention="30 days",  # Keep logs for 30 days
        compression="zip",  # Compress rotated logs
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{line} - {message}"
    )
    
    # 2. Debug logs (all levels)
    logger.add(
        "logs/app/debug_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="7 days",
        compression="zip",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{line} - {message}"
    )
    
    # 3. Access logs (for requests)
    logger.add(
        "logs/access/access_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        compression="zip",
        filter=lambda record: record["function"] == "log_request_info",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}"
    )
    
    # 4. Error logs (WARNING and above)
    logger.add(
        "logs/error/error_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="60 days",
        compression="zip",
        level="WARNING",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{line} - {message}"
    )
    
    # 5. Performance logs
    logger.add(
        "logs/performance/perf_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        compression="zip",
        filter=lambda record: "Performance:" in record["message"],
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}"
    )
    
    logger.info(f"Logging initialized with level {log_level}")

# Call setup_logging at module level
setup_logging()

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__, template_folder="templates")
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
                
            # Skip Flask view functions (проверяем несколько атрибутов)
            if hasattr(attr, 'view_class') or hasattr(attr, '_is_view') or hasattr(attr, '__blueprints__'):
                continue
                
            # Проверяем, является ли функция маршрутом Flask
            if hasattr(attr, '__module__') and 'flask' in attr.__module__:
                continue
                
            # Дополнительная проверка для маршрутов Blueprint
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
    
    # Проверяем, авторизован ли пользователь
    if 'spotify_token' in session:
        logger.info(f"User is authenticated: {session.get('username', 'Unknown')}")
    else:
        logger.info("User is not authenticated")
    
    return render_template('home.html')

@app.route('/api/recommendations')
def get_recommendations_api():
    """
    Asynchronously fetch music recommendations based on user's top tracks.
    
    This endpoint is called via AJAX to load recommendations without refreshing the page.
    It uses the user's top tracks stored in the session to generate personalized
    recommendations from Spotify API. Implements retry logic for rate limiting.
    
    Returns:
        JSON response containing recommended tracks data or an empty list/error message
    """
    request_id = str(uuid.uuid4())[:8]  # Создаем короткий ID запроса для отслеживания
    logger.info(f"[{request_id}] Async request for recommendations received")

    if "spotify_token" not in session:
        logger.error(f"[{request_id}] No Spotify token in session for async recommendations")
        return jsonify({"error": "Not authenticated"}), 401

    # Check for tracks in session
    logger.debug(f"[{request_id}] Session keys: {list(session.keys())}")

    # Get track IDs from session
    if "top_track_ids" in session and session["top_track_ids"]:
        track_ids = session["top_track_ids"]
        logger.info(f"[{request_id}] Using {len(track_ids)} track IDs from session for recommendations")
        logger.debug(f"[{request_id}] Track IDs: {track_ids}")
    else:
        # If no track IDs in session, fetch them again
        logger.info(f"[{request_id}] No track IDs in session, fetching top tracks")
        top_tracks = get_top_tracks()
        if not top_tracks:
            logger.error(f"[{request_id}] Failed to get top tracks for recommendations")
            return jsonify([])

        # Save track IDs, max 5 for diverse recommendations
        track_ids = [track["id"] for track in top_tracks[:5]]
        session["top_track_ids"] = track_ids
        logger.info(f"[{request_id}] Saved {len(track_ids)} track IDs to session")
        logger.debug(f"[{request_id}] New track IDs: {track_ids}")

    try:
        # Get recommendations with retry on 429 error
        logger.info(f"[{request_id}] Fetching recommendations from Spotify API")
        start_time = datetime.now()

        # Add retry mechanism
        max_retries = 3
        retry_delay = 2
        all_recommendations = []

        # Use up to 3 tracks for diverse recommendations
        seed_tracks = track_ids[:3] if len(track_ids) >= 3 else track_ids
        logger.info(f"[{request_id}] Using {len(seed_tracks)} seed tracks for diverse recommendations: {seed_tracks}")

        if not seed_tracks:
            logger.error(f"[{request_id}] No seed tracks available")
            return jsonify([])

        # Get recommendations for each track separately
        for i, seed_track in enumerate(seed_tracks):
            logger.info(f"[{request_id}] Getting recommendations for seed track {i+1}/{len(seed_tracks)}: {seed_track}")

            # Add delay between requests to avoid 429 error
            if i > 0:
                logger.debug(f"[{request_id}] Waiting 2 seconds before next request to avoid rate limiting")
                time.sleep(2)

            for attempt in range(max_retries):
                try:
                    # Get recommendations for one track
                    logger.debug(f"[{request_id}] Calling get_recommendations() for track {seed_track}, attempt {attempt+1}/{max_retries}")
                    track_recommendations = get_recommendations([seed_track])
                    
                    if track_recommendations:
                        logger.info(f"[{request_id}] Received {len(track_recommendations)} recommendations for track {seed_track}")
                        # Take only first 4 recommendations for each track
                        all_recommendations.extend(track_recommendations[:4])
                        logger.debug(f"[{request_id}] Added {min(4, len(track_recommendations))} recommendations to results")
                        break
                    else:
                        logger.warning(f"[{request_id}] No recommendations returned for track {seed_track}")
                        
                except Exception as e:
                    error_msg = str(e)
                    logger.error(
                        f"[{request_id}] Error in attempt {attempt+1}/{max_retries} for track {seed_track}: {error_msg}",
                        exc_info=True
                    )

                    if "429" in error_msg and attempt < max_retries - 1:
                        logger.warning(
                            f"[{request_id}] Rate limit hit, retrying in {retry_delay} seconds (attempt {attempt+1}/{max_retries})"
                        )
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        # Continue with next track
                        logger.warning(f"[{request_id}] Skipping track {seed_track} after {attempt+1} failed attempts")
                        break

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.info(
            f"[{request_id}] All recommendations fetch completed in {duration:.2f} seconds, got {len(all_recommendations)} total recommendations"
        )

        # Check that recommendations are not empty
        if not all_recommendations:
            logger.error(f"[{request_id}] No recommendations found after trying all seed tracks")
            return jsonify([])  # Return empty list instead of error

        # Remove duplicates by ID
        unique_recommendations = []
        seen_ids = set()
        for track in all_recommendations:
            if track["id"] not in seen_ids:
                seen_ids.add(track["id"])
                unique_recommendations.append(track)

        logger.info(
            f"[{request_id}] Processing {len(unique_recommendations)} unique recommendations for response (removed {len(all_recommendations) - len(unique_recommendations)} duplicates)"
        )

        # Convert recommendations to JSON format (minimize data)
        recommendations_data = []
        for i, track in enumerate(unique_recommendations[:10]):  # Limit to 10 recommendations
            # Minimize data, keep only what's necessary
            try:
                # Проверяем наличие обложки альбома
                album_image = ""
                if track.get("album") and track["album"].get("images") and track["album"]["images"]:
                    album_image = track["album"]["images"][0]["url"]
                    logger.debug(f"[{request_id}] Track {i+1} album image: {album_image}")
                else:
                    logger.warning(f"[{request_id}] No album image found for track {track['id']} - {track['name']}")
                
                track_data = {
                    "id": track["id"],
                    "name": track["name"],
                    "artist": (
                        track["artists"][0]["name"] if track["artists"] else "Unknown"
                    ),
                    "album_image": album_image,
                    "url": track["external_urls"].get("spotify", ""),
                }
                recommendations_data.append(track_data)
                logger.debug(f"[{request_id}] Processed track {i+1}: {track['name']} by {track_data['artist']}")
            except Exception as e:
                logger.error(f"[{request_id}] Error processing track {i+1}: {str(e)}", exc_info=True)
                # Continue with next track

        logger.info(f"[{request_id}] Returning {len(recommendations_data)} recommendations")
        return jsonify(recommendations_data)

    except AppError as e:
        # AppErrors are already formatted properly
        logger.error(f"AppError in recommendations API: {str(e)}", exc_info=True)
        return jsonify({
            "error": True,
            "message": str(e),
            "error_code": e.error_code,
            "error_id": e.error_id
        }), 500
    except Exception as e:
        # Unexpected errors
        logger.error(f"Unexpected error in recommendations API: {str(e)}", exc_info=True)
        error_id = str(uuid.uuid4())
        return jsonify({
            "error": True,
            "message": f"An unexpected error occurred: {str(e)}",
            "error_id": error_id
        }), 500

@app.route('/profile')
def profile():
    """Render the user profile page."""
    logger.info("Rendering profile page")
    logger.debug(f"Session in profile: {session}")
    
    # Проверяем, авторизован ли пользователь
    if 'spotify_token' not in session:
        logger.info("User not authenticated, showing login button")
        return render_template('profile.html', show_login_button=True)
    
    # Получаем топ треки пользователя
    try:
        headers = get_headers()
        if not headers:
            logger.warning("Failed to get valid headers, showing login button")
            return render_template('profile.html', show_login_button=True)
        
        # Получаем топ треки
        top_tracks = get_top_tracks(headers)
        
        # Проверяем, является ли пользователь премиум-пользователем
        premium_user = is_premium_user()
        
        logger.info(f"Rendering profile with {len(top_tracks)} top tracks")
        return render_template(
            'profile.html', 
            show_login_button=False, 
            top_tracks=top_tracks,
            premium_user=premium_user
        )
    except Exception as e:
        logger.error(f"Error rendering profile: {str(e)}", exc_info=True)
        # В случае ошибки показываем страницу с кнопкой входа
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
    return redirect(url_for('get_recommendations_api'))

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

# Call initialization
if __name__ == "__main__":
    init_app()
    logger.info("Starting Flask application in debug mode")
    app.run(debug=True)

# Инициализация сессии
Session(app)
