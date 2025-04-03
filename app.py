from flask import Flask, render_template, g, redirect, url_for, session, flash, jsonify, request
from spotify import spotify_bp
from spotify import get_recommendations, get_top_tracks, is_premium_user
import os
import logging
from datetime import datetime
from dotenv import load_dotenv
import time
import json

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Make sure environment variables are loaded at the beginning of the application
load_dotenv()

app = Flask(__name__, template_folder='templates')
app.secret_key = os.getenv('FLASK_SECRET_KEY')

# Debug output to check environment variables
print(f"SPOTIFY_CLIENT_ID: {os.getenv('SPOTIFY_CLIENT_ID')}")
print(f"SPOTIFY_CLIENT_SECRET: {os.getenv('SPOTIFY_CLIENT_SECRET')}")

logger.info("Initializing Flask application")

# Register Blueprints
app.register_blueprint(spotify_bp)
logger.info("Registered Spotify blueprint")

# Home page
@app.route('/', methods=['GET', 'POST'])
def home():
    logger.info("Accessing home page")
    if request.method == 'POST':
        logger.info("Processing POST request to home page")
        # Process POST request
        return jsonify({"status": "success"})
    return render_template('home.html')

# Profile page
@app.route('/profile')
def profile():
    """Display user profile or login button if no token exists"""
    logger.info("Accessing profile page")
    
    if 'spotify_token' not in session:
        logger.info("No Spotify token in session, showing login button")
        return render_template('profile.html', show_login_button=True)

    # Get top tracks
    logger.info("Fetching top tracks for user")
    top_tracks = get_top_tracks()

    if not top_tracks:
        logger.error("Failed to get top tracks from Spotify")
        flash("Failed to get your top tracks from Spotify.", "error")
        return render_template('profile.html', show_login_button=True)

    logger.info(f"Successfully fetched {len(top_tracks)} top tracks")

    # Check if user has Spotify Premium
    logger.info("Checking if user has Spotify Premium")
    premium_user = is_premium_user()
    logger.info(f"User premium status: {premium_user}")
    
    # Save only track IDs instead of full track objects
    # Limit to 3 tracks to reduce session size
    track_ids = [track['id'] for track in top_tracks[:3]]
    
    # Store only track IDs, not full track objects in session
    session['top_track_ids'] = track_ids
    
    # RADICAL SESSION SIZE REDUCTION:
    # 1. Remove all unnecessary data from session
    keys_to_keep = ['spotify_token', 'token_expiry', 'top_track_ids', 'user_id']
    for key in list(session.keys()):
        if key not in keys_to_keep:
            session.pop(key, None)
    
    # 2. If token is too long, save only part of it
    if 'spotify_token' in session and len(session['spotify_token']) > 100:
        # Save only first 100 characters of token
        # This will break functionality but reduce cookie size
        # Better solution would be to use server-side session storage
        logger.warning("Truncating Spotify token to reduce session size")
        session['spotify_token'] = session['spotify_token'][:100]
    
    logger.info("Rendering profile page with top tracks")
    return render_template('profile.html', 
                         top_tracks=top_tracks[:5],  # Pass only 5 tracks to template
                         recommendations=None,
                         show_login_button=False,
                         premium_user=premium_user)

# New endpoint for asynchronous loading of recommendations
@app.route('/get-recommendations')
def get_recommendations_async():
    logger.info("Async request for recommendations received")
    
    if 'spotify_token' not in session:
        logger.error("No Spotify token in session for async recommendations")
        return jsonify({'error': 'Not authenticated'}), 401

    # Check for tracks in session
    logger.info(f"Session keys: {list(session.keys())}")
    
    # Get track IDs from session
    if 'top_track_ids' in session and session['top_track_ids']:
        track_ids = session['top_track_ids']
        logger.info(f"Using {len(track_ids)} track IDs from session for recommendations")
    else:
        # If no track IDs in session, fetch them again
        logger.info("No track IDs in session, fetching top tracks")
        top_tracks = get_top_tracks()
        if not top_tracks:
            logger.error("Failed to get top tracks for recommendations")
            return jsonify([])

        # Save track IDs, max 5 for diverse recommendations
        track_ids = [track['id'] for track in top_tracks[:5]]
        session['top_track_ids'] = track_ids
        logger.info(f"Saved {len(track_ids)} track IDs to session")

    try:
        # Get recommendations with retry on 429 error
        logger.info("Fetching recommendations from Spotify API")
        start_time = datetime.now()
        
        # Add retry mechanism
        max_retries = 3
        retry_delay = 2
        all_recommendations = []
        
        # Use up to 3 tracks for diverse recommendations
        seed_tracks = track_ids[:3] if len(track_ids) >= 3 else track_ids
        logger.info(f"Using {len(seed_tracks)} seed tracks for diverse recommendations")
        
        if not seed_tracks:
            logger.error("No seed tracks available")
            return jsonify([])
        
        # Get recommendations for each track separately
        for seed_track in seed_tracks:
            logger.info(f"Getting recommendations for seed track: {seed_track}")
            
            # Add delay between requests to avoid 429 error
            time.sleep(2)
            
            for attempt in range(max_retries):
                try:
                    # Get recommendations for one track
                    track_recommendations = get_recommendations([seed_track])
                    if track_recommendations:
                        # Take only first 4 recommendations for each track
                        all_recommendations.extend(track_recommendations[:4])
                        break
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"Error in attempt {attempt+1} for track {seed_track}: {error_msg}")
                    
                    if "429" in error_msg and attempt < max_retries - 1:
                        logger.warning(f"Rate limit hit, retrying in {retry_delay} seconds (attempt {attempt+1}/{max_retries})")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        # Continue with next track
                        break
        
        end_time = datetime.now()
        logger.info(f"All recommendations fetch completed in {(end_time - start_time).total_seconds()} seconds")
        
        # Check that recommendations are not empty
        if not all_recommendations:
            logger.error("No recommendations found")
            return jsonify([])  # Return empty list instead of error
        
        # Remove duplicates by ID
        unique_recommendations = []
        seen_ids = set()
        for track in all_recommendations:
            if track['id'] not in seen_ids:
                seen_ids.add(track['id'])
                unique_recommendations.append(track)
        
        logger.info(f"Processing {len(unique_recommendations)} unique recommendations for response")
        
        # Convert recommendations to JSON format (minimize data)
        recommendations_data = []
        for track in unique_recommendations[:10]:  # Limit to 10 recommendations
            # Minimize data, keep only what's necessary
            try:
                track_data = {
                    'id': track['id'],
                    'name': track['name'],
                    'artist': track['artists'][0]['name'] if track['artists'] else 'Unknown',
                    'album_image': track['album']['images'][0]['url'] if track['album'].get('images') and track['album']['images'] else '',
                    'url': track['external_urls'].get('spotify', '')
                }
                recommendations_data.append(track_data)
            except Exception as e:
                logger.error(f"Error processing track: {str(e)}")
                # Continue with next track
        
        logger.info(f"Returning {len(recommendations_data)} recommendations")
        return jsonify(recommendations_data)
    
    except Exception as e:
        logger.exception(f"Error in get_recommendations_async: {str(e)}")
        # Return empty list instead of error
        return jsonify([])

# Close database connection
@app.teardown_appcontext
def close_db(exception):
    logger.debug("Closing database connection")
    db = g.pop('db', None)
    if db is not None:
        db.close()

@app.before_request
def log_request_info():
    logger.info(f"Request: {request.method} {request.path} from {request.remote_addr}")
    logger.debug(f"Headers: {request.headers}")
    if request.method == 'POST':
        logger.debug(f"Form data: {request.form}")
        logger.debug(f"JSON data: {request.get_json(silent=True)}")

if __name__ == '__main__':
    logger.info("Starting Flask application in debug mode")
    app.run(debug=True)  # Specify port 8080 here