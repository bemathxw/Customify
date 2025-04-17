import time
import functools
import json
import os
from datetime import datetime
from flask import request, session, g
from loguru import logger

# Directory for storing user tracking data
PROFILE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'profiling_results', 'user_tracking')
os.makedirs(PROFILE_DIR, exist_ok=True)

# Dictionary to store user tracking metrics
_user_metrics = {
    'page_views': {},
    'errors': {},
    'recommendations': {
        'total': 0,
        'liked': 0,
        'skipped': 0,
        'details': []
    },
    'playlists': {
        'created': 0,
        'tracks_added': 0,
        'details': []
    }
}

def profile_function(func):
    """
    Decorator for profiling function execution time.
    
    Args:
        func: The function to profile
        
    Returns:
        Decorated function
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            
            # Log execution time
            logger.debug(f"Function {func.__name__} executed in {duration:.4f} seconds")
            
            return result
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Function {func.__name__} failed after {duration:.4f} seconds: {str(e)}")
            raise
            
    return wrapper

def track_page_view(page_name):
    """
    Track a page view.
    
    Args:
        page_name (str): Name of the page being viewed
    """
    if page_name not in _user_metrics['page_views']:
        _user_metrics['page_views'][page_name] = 0
        
    _user_metrics['page_views'][page_name] += 1
    
    logger.debug(f"Page view tracked: {page_name}")

def track_user_error(error_type, error_message, page=None):
    """
    Track a user-facing error.
    
    Args:
        error_type (str): Type of error
        error_message (str): Error message
        page (str, optional): Page where error occurred
    """
    if error_type not in _user_metrics['errors']:
        _user_metrics['errors'][error_type] = {
            'count': 0,
            'instances': []
        }
    
    _user_metrics['errors'][error_type]['count'] += 1
    _user_metrics['errors'][error_type]['instances'].append({
        'message': error_message,
        'page': page,
        'timestamp': datetime.now().isoformat(),
        'user_id': session.get('user_id', 'anonymous')
    })
    
    logger.warning(f"User error tracked: {error_type} - {error_message}")

def track_recommendation_interaction(action, track_id=None, genre=None):
    """
    Track user interaction with recommendations.
    
    Args:
        action (str): Type of interaction (like, skip, etc.)
        track_id (str, optional): ID of the track
        genre (str, optional): Genre of the track
    """
    _user_metrics['recommendations']['total'] += 1
    
    if action == 'like':
        _user_metrics['recommendations']['liked'] += 1
    elif action == 'skip':
        _user_metrics['recommendations']['skipped'] += 1
    
    _user_metrics['recommendations']['details'].append({
        'action': action,
        'track_id': track_id,
        'genre': genre,
        'timestamp': datetime.now().isoformat(),
        'user_id': session.get('user_id', 'anonymous')
    })
    
    logger.debug(f"Recommendation interaction tracked: {action} for track {track_id}")

def track_playlist_interaction(action, playlist_id=None, track_count=None):
    """
    Track user interaction with playlists.
    
    Args:
        action (str): Type of interaction (create, add, etc.)
        playlist_id (str, optional): ID of the playlist
        track_count (int, optional): Number of tracks in the playlist
    """
    if action == 'create':
        _user_metrics['playlists']['created'] += 1
        
    if track_count:
        _user_metrics['playlists']['tracks_added'] += track_count
    
    _user_metrics['playlists']['details'].append({
        'action': action,
        'playlist_id': playlist_id,
        'track_count': track_count,
        'timestamp': datetime.now().isoformat(),
        'user_id': session.get('user_id', 'anonymous')
    })
    
    logger.debug(f"Playlist interaction tracked: {action} with {track_count} tracks")

def get_user_metrics():
    """
    Get all user tracking metrics.
    
    Returns:
        dict: Dictionary of user metrics
    """
    return _user_metrics

def save_user_metrics_to_file():
    """
    Save current user metrics to a file.
    
    Returns:
        str: Path to the saved file
    """
    metrics = get_user_metrics()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = os.path.join(PROFILE_DIR, f"user_metrics_{timestamp}.json")
    
    with open(filename, 'w') as f:
        json.dump(metrics, f, indent=2)
        
    logger.info(f"User metrics saved to {filename}")
    return filename

def reset_user_metrics():
    """Reset all user tracking metrics."""
    global _user_metrics
    _user_metrics = {
        'page_views': {},
        'errors': {},
        'recommendations': {
            'total': 0,
            'liked': 0,
            'skipped': 0,
            'details': []
        },
        'playlists': {
            'created': 0,
            'tracks_added': 0,
            'details': []
        }
    }
    logger.info("User metrics reset") 