import requests
import time
import logging
from datetime import datetime
from flask import Blueprint, redirect, request, session, url_for, flash, render_template
from urllib.parse import urlencode
import os
import random

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

spotify_bp = Blueprint('spotify', __name__)

# Spotify OAuth2 settings
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
SPOTIFY_REDIRECT_URI = "http://127.0.0.1:5000/spotify/callback"

SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1"
SCOPE = "user-read-private user-read-email user-top-read playlist-modify-private"
SHOW_DIALOG = "true"

@spotify_bp.route('/clear')
def clear_spotify_tokens():
    """Clear all Spotify tokens from session"""
    logger.info("Clearing Spotify tokens from session")
    session.pop('spotify_token', None)
    session.pop('spotify_refresh_token', None)
    session.pop('spotify_token_expires_in', None)
    logger.info("Spotify tokens cleared from session")
    return redirect('profile')


def is_token_expired():
    expires_at = session.get('spotify_token_expires_in')
    is_expired = expires_at and time.time() > expires_at
    logger.info(f"Checking if token is expired: {is_expired}")
    return is_expired


def refresh_spotify_token():
    """Refresh access_token using refresh_token"""
    logger.info("Attempting to refresh Spotify token")
    refresh_token = session.get('spotify_refresh_token')

    if not refresh_token:
        logger.warning("No refresh token available. Clearing session and redirecting to login.")
        clear_spotify_tokens()
        return redirect(url_for('spotify.login_spotify'))

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": SPOTIFY_CLIENT_ID,
        "client_secret": SPOTIFY_CLIENT_SECRET
    }

    logger.info("Sending refresh token request to Spotify")
    response = requests.post(SPOTIFY_TOKEN_URL, data=payload)
    response_data = response.json()

    if response.status_code != 200:
        logger.error(f"Failed to refresh token: {response_data}. Clearing session and redirecting to login.")
        clear_spotify_tokens()
        return False

    # Update token in session
    session['spotify_token'] = response_data['access_token']
    session['spotify_token_expires_in'] = time.time() + response_data['expires_in']
    logger.info("Token refreshed successfully")
    return True


def get_headers():
    """Return headers with token for Spotify API, refresh token if necessary"""
    if 'spotify_token' not in session:
        print("No token found in session, redirecting to login.")
        return None

    if is_token_expired():
        print("Token expired, attempting to refresh...")
        if not refresh_spotify_token():
            print("Failed to refresh token, clearing session and redirecting to login.")
            clear_spotify_tokens()
            return None

    return {
        'Authorization': f"Bearer {session.get('spotify_token')}"
    }


@spotify_bp.route('/login-spotify')
def login_spotify():
    logger.info("Initiating Spotify login process")
    auth_query_parameters = {
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": SCOPE,
        "client_id": SPOTIFY_CLIENT_ID,
        "show_dialog": SHOW_DIALOG
    }
    url_args = urlencode(auth_query_parameters)
    auth_url = f"{SPOTIFY_AUTH_URL}/?{url_args}"
    logger.info(f"Redirecting to Spotify auth URL: {auth_url}")
    return redirect(auth_url)


@spotify_bp.route('/spotify/callback')
def callback():
    logger.info("Received callback from Spotify")
    auth_token = request.args.get('code')

    if not auth_token:
        logger.error("Authorization failed. No code provided.")
        flash("Authorization failed. No code provided.", "error")
        return redirect(url_for('profile'))

    payload = {
        "grant_type": "authorization_code",
        "code": auth_token,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "client_id": SPOTIFY_CLIENT_ID,
        "client_secret": SPOTIFY_CLIENT_SECRET
    }

    logger.info("Exchanging auth code for access token")
    response = requests.post(SPOTIFY_TOKEN_URL, data=payload)
    response_data = response.json()

    if response.status_code != 200:
        logger.error(f"Failed to authenticate with Spotify: {response_data}")
        flash(f"Failed to authenticate with Spotify: {response_data}", "error")
        return redirect(url_for('profile'))

    # Save token in session
    session['spotify_token'] = response_data['access_token']
    session['spotify_refresh_token'] = response_data.get('refresh_token')
    session['spotify_token_expires_in'] = time.time() + response_data['expires_in']
    logger.info("Successfully authenticated with Spotify")

    # Redirect to recommendations page
    logger.info("Redirecting to recommendations page")
    return redirect(url_for('spotify.spotify_recommendations'))


def get_top_tracks():
    """Get user's top tracks"""
    headers = get_headers()
    if not headers:
        return []

    # Check cache in session
    cache_key = 'cached_top_tracks'
    cache_time_key = 'cached_top_tracks_time'
    current_time = time.time()
    
    # Use cache if it exists and is less than 1 hour old
    if cache_key in session and cache_time_key in session:
        if current_time - session[cache_time_key] < 3600:  # 1 hour = 3600 seconds
            print("Using cached top tracks in get_top_tracks")
            return session[cache_key]

    # Get top tracks
    top_tracks_url = f"{SPOTIFY_API_BASE_URL}/me/top/tracks?time_range=short_term&limit=10"
    response = requests.get(top_tracks_url, headers=headers)
    
    if response.status_code != 200:
        print(f"Error fetching top tracks: {response.status_code}, {response.text}")
        return []
    
    top_tracks = response.json().get('items', [])
    
    # Save to cache
    session[cache_key] = top_tracks
    session[cache_time_key] = current_time
    
    return top_tracks


# Get recommendations based on user's tracks
def get_recommendations(track_ids):
    """Get recommendations from random tracks of all artists in top-10"""
    headers = get_headers()
    if not headers:
        return []

    all_track_ids = []
    processed_artists = set()  # To track already processed artists

    # Go through each track from top-10
    for track_id in track_ids:
        # Get track information
        track_url = f"{SPOTIFY_API_BASE_URL}/tracks/{track_id}"
        track_response = requests.get(track_url, headers=headers)
        
        if track_response.status_code != 200:
            print(f"Error fetching track info: {track_response.status_code}, {track_response.text}")
            continue
        
        # Get artist ID
        artist_id = track_response.json()['artists'][0]['id']
        
        # Skip if artist already processed
        if artist_id in processed_artists:
            continue
        processed_artists.add(artist_id)
        
        # Get artist's albums
        artist_albums_url = f"{SPOTIFY_API_BASE_URL}/artists/{artist_id}/albums"
        albums_response = requests.get(artist_albums_url, headers=headers, params={'limit': 20})
        
        if albums_response.status_code != 200:
            print(f"Error fetching artist albums: {albums_response.status_code}, {albums_response.text}")
            continue
        
        # Collect tracks from albums
        for album in albums_response.json().get('items', []):
            album_tracks_url = f"{SPOTIFY_API_BASE_URL}/albums/{album['id']}/tracks"
            tracks_response = requests.get(album_tracks_url, headers=headers)
            
            if tracks_response.status_code == 200:
                album_tracks = tracks_response.json().get('items', [])
                # Add only one random track from album
                if album_tracks:
                    random_track = random.choice(album_tracks)
                    all_track_ids.append(random_track['id'])
    
    # Remove tracks that are already in user's top
    all_track_ids = [tid for tid in all_track_ids if tid not in track_ids]
    
    # Select random 10 tracks
    if len(all_track_ids) > 10:
        selected_track_ids = random.sample(all_track_ids, 10)
    else:
        selected_track_ids = all_track_ids
    
    # Get full information about selected tracks
    tracks_url = f"{SPOTIFY_API_BASE_URL}/tracks"
    params = {
        'ids': ','.join(selected_track_ids),
        'market': 'US'
    }
    
    response = requests.get(tracks_url, headers=headers, params=params)
    
    if response.status_code != 200:
        print(f"Error fetching selected tracks: {response.status_code}, {response.text}")
        return []
    
    tracks = response.json().get('tracks', [])
    
    # Save track IDs in session
    session['recommended_tracks'] = [track['id'] for track in tracks]
    
    print(f"Generated {len(tracks)} random recommendations from multiple artists")
    return tracks


@spotify_bp.route('/spotify/recommendations')
def spotify_recommendations():
    logger.info("Accessing spotify recommendations page")

    if 'spotify_token' not in session:
        logger.warning("No Spotify token in session")
        flash("You need to log in with Spotify to get recommendations.", "error")
        return redirect(url_for('spotify.login_spotify'))

    logger.info("Fetching top tracks for user")
    top_tracks = get_top_tracks()

    if not top_tracks:
        logger.error("Failed to get top tracks from Spotify")
        flash("Failed to get your top tracks from Spotify.", "error")
        return redirect(url_for('profile'))

    logger.info(f"Successfully fetched {len(top_tracks)} top tracks")
    
    # Check if user is a premium user
    logger.info("Checking if user has Spotify Premium")
    premium_user = is_premium_user()
    logger.info(f"User premium status: {premium_user}")
    
    # Save track IDs in session for later use
    track_ids = [track['id'] for track in top_tracks]
    session['top_track_ids'] = track_ids
    logger.info(f"Saved {len(track_ids)} top track IDs to session")

    # Display page without recommendations, they will be loaded asynchronously
    logger.info("Rendering profile page with top tracks, recommendations will load asynchronously")
    return render_template('profile.html', 
                          top_tracks=top_tracks, 
                          recommendations=None,  # Recommendations will be loaded asynchronously
                          show_login_button=False,
                          premium_user=premium_user)

@spotify_bp.route('/spotify/add_recommendations_to_queue', methods=['POST'])
def add_recommendations_to_queue():
    if is_premium_user():

        if 'spotify_token' not in session:
            flash("You need to log in with Spotify to add tracks to your queue.", "error")
            return redirect(url_for('spotify.login_spotify'))

        top_tracks = get_top_tracks()
        track_ids = [track['id'] for track in top_tracks]

        recommendations = get_recommendations(track_ids)
        if not recommendations:
            flash("No recommendations available to add.", "error")
            return redirect(url_for('profile'))

        headers = get_headers()
        if not headers:
            flash("Failed to authenticate with Spotify.", "error")
            return redirect(url_for('spotify.login_spotify'))

        for track in recommendations:
            track_uri = f"spotify:track:{track['id']}"
            queue_url = f"https://api.spotify.com/v1/me/player/queue?uri={track_uri}"

            response = requests.post(queue_url, headers=headers)
            if response.status_code != 204:
                print(f"Failed to add track {track['name']} to the queue: {response.status_code}, {response.text}")
            else:
                print(f"Track {track['name']} successfully added to the queue.")

        flash("All recommended tracks added to your queue!", "success")
        return redirect(url_for('profile'))
    else:
        return redirect(url_for('profile'))

def is_premium_user():

    user_profile_url = "https://api.spotify.com/v1/me"
    headers = get_headers()
    response = requests.get(user_profile_url, headers=headers)

    if response.status_code == 200:
        user_data = response.json()
        return user_data.get('product') == 'premium'
    else:
        print(f"Failed to fetch user profile: {response.status_code}, {response.text}")
        return False

def create_playlist(headers):
    user_data = get_current_user(headers)
    if not user_data:
        return None

    user_id = user_data.get('id')
    create_playlist_url = f"https://api.spotify.com/v1/users/{user_id}/playlists"
    playlist_name = "Saved recommendations"
    payload = {
        "name": playlist_name,
        "description": "Playlist created from your saved recommendations",
        "public": False
    }

    print(f"Creating playlist with name: {playlist_name} for user {user_id}")

    response = requests.post(create_playlist_url, json=payload, headers=headers)
    if response.status_code == 201:
        playlist_id = response.json()['id']
        print(f"Playlist created successfully: {playlist_id}")
        return playlist_id
    else:
        print(f"Error creating playlist: {response.status_code}, {response.text}")
        return None


def add_tracks_to_playlist(playlist_id, track_uris, headers):
    add_tracks_url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
    payload = {
        "uris": track_uris
    }

    print(f"Adding tracks to playlist {playlist_id}: {track_uris}")

    response = requests.post(add_tracks_url, json=payload, headers=headers)
    if response.status_code == 201:
        print("Tracks successfully added to playlist!")
    else:
        print(f"Error adding tracks to playlist: {response.status_code}, {response.text}")


@spotify_bp.route('/add-to-playlist', methods=['POST'])
def add_to_playlist():
    headers = get_headers()

    user_data = get_current_user(headers)
    if not user_data:
        print("Failed to get user profile.")
        return redirect(url_for('profile'))

    user_id = user_data.get('id')

    recommended_track_ids = session.get('recommended_tracks', [])
    if not recommended_track_ids:
        print("No recommended tracks available.")
        return redirect(url_for('profile'))

    playlist_id = create_playlist(headers)
    if playlist_id:
        
        track_uris = [f"spotify:track:{track_id}" for track_id in recommended_track_ids]
        add_tracks_to_playlist(playlist_id, track_uris, headers)
        print(f"Tracks added to playlist: {playlist_id}")
    else:
        print("Failed to create playlist.")

    return redirect(url_for('profile'))



def get_current_user(headers):
    user_profile_url = f"{SPOTIFY_API_BASE_URL}/me"
    response = requests.get(user_profile_url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error fetching user profile: {response.status_code}, {response.text}")
        return None
