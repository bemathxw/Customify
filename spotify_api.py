import os
import time
import requests
from flask import session
from loguru import logger
import random

from errors import AppError, SpotifyAPIError, AuthenticationError, DataProcessingError, catch_exceptions

# Spotify API endpoints
SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1"

# Get Spotify credentials from environment variables
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")

# Spotify API scopes
SPOTIFY_SCOPES = [
    "user-read-private",
    "user-read-email",
    "user-top-read",
    "playlist-modify-public",
    "playlist-modify-private"
]

@catch_exceptions
def refresh_spotify_token():
    """
    Refresh access_token using refresh_token.
    
    Attempts to use the stored refresh token to obtain a new access token
    from Spotify's API.
    
    Returns:
        bool: True if token was successfully refreshed, False otherwise
        
    Raises:
        AuthenticationError: If refresh token is missing or invalid
        SpotifyAPIError: If Spotify API returns an error
    """
    logger.info("Attempting to refresh Spotify token")
    refresh_token = session.get("spotify_refresh_token")

    if not refresh_token:
        raise AuthenticationError(
            "No refresh token available for token refresh",
            context={"session_keys": list(session.keys())}
        )

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": SPOTIFY_CLIENT_ID,
        "client_secret": SPOTIFY_CLIENT_SECRET,
    }

    logger.info("Sending refresh token request to Spotify")
    try:
        response = requests.post(SPOTIFY_TOKEN_URL, data=payload)
        response_data = response.json()

        if response.status_code != 200:
            raise SpotifyAPIError(
                f"Failed to refresh token: {response_data.get('error_description', 'Unknown error')}",
                status_code=response.status_code,
                endpoint=SPOTIFY_TOKEN_URL,
                context={"response": response_data}
            )

        # Update token in session
        session["spotify_token"] = response_data["access_token"]
        session["spotify_token_expires_in"] = time.time() + response_data["expires_in"]
        logger.info("Token refreshed successfully")
        return True
        
    except requests.RequestException as e:
        raise SpotifyAPIError(
            f"Network error during token refresh: {str(e)}",
            endpoint=SPOTIFY_TOKEN_URL
        )

@catch_exceptions
def get_headers():
    """
    Get authorization headers for Spotify API requests.
    
    This function checks if the current token is valid and refreshes it if needed.
    
    Returns:
        dict: Headers with authorization token or None if not authenticated
    """
    # Проверяем, есть ли токен в сессии
    if 'spotify_token' not in session:
        logger.warning("No Spotify token in session")
        return None
    
    # Проверяем, не истек ли токен
    if 'spotify_token_expires_in' in session and time.time() > session['spotify_token_expires_in']:
        logger.info("Spotify token expired, refreshing")
        
        # Проверяем, есть ли refresh token
        if 'spotify_refresh_token' not in session:
            logger.warning("No refresh token available")
            return None
        
        # Обновляем токен
        refresh_token = session['spotify_refresh_token']
        
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": SPOTIFY_CLIENT_ID,
            "client_secret": SPOTIFY_CLIENT_SECRET
        }
        
        try:
            response = requests.post(SPOTIFY_TOKEN_URL, data=payload)
            
            if response.status_code != 200:
                logger.warning(f"Failed to refresh token: {response.status_code}")
                # Очищаем сессию, так как токен недействителен
                session.pop('spotify_token', None)
                session.pop('spotify_token_expires_in', None)
                return None
                
            token_data = response.json()
            
            # Обновляем токен в сессии
            session['spotify_token'] = token_data['access_token']
            session['spotify_token_expires_in'] = time.time() + token_data['expires_in']
            
            # Если в ответе есть новый refresh token, обновляем его
            if 'refresh_token' in token_data:
                session['spotify_refresh_token'] = token_data['refresh_token']
                
            logger.info("Successfully refreshed Spotify token")
        except Exception as e:
            logger.error(f"Error refreshing token: {str(e)}")
            return None
    
    # Возвращаем заголовки с токеном
    headers = {
        "Authorization": f"Bearer {session['spotify_token']}"
    }
    logger.debug(f"Headers: {headers}")
    return headers

@catch_exceptions
def get_current_user(headers=None):
    """
    Get the current user's Spotify profile.
    
    Args:
        headers (dict, optional): Authorization headers. If not provided,
                                 they will be fetched using get_headers().
                                 
    Returns:
        dict: User profile data or None if request fails
    """
    if headers is None:
        headers = get_headers()
        if not headers:
            logger.warning("No valid headers for get_current_user")
            return None
    
    try:
        response = requests.get(f"{SPOTIFY_API_BASE_URL}/me", headers=headers)
        
        if response.status_code != 200:
            logger.warning(f"Failed to get user profile: {response.status_code}")
            return None
            
        return response.json()
    except Exception as e:
        logger.error(f"Error getting user profile: {str(e)}")
        return None

@catch_exceptions
def get_top_tracks(headers=None, limit=10, time_range="short_term"):
    """
    Get user's top tracks from Spotify.
    
    Args:
        headers (dict): Authorization headers (optional, will be fetched if not provided)
        limit (int): Number of tracks to return (default: 10)
        time_range (str): Time range for top tracks - 'short_term', 'medium_term', or 'long_term' (default: 'medium_term')
    
    Returns:
        list: List of track objects
        
    Raises:
        SpotifyAPIError: If Spotify API returns an error
        AuthenticationError: If headers are invalid
    """
    if not headers:
        headers = get_headers()
        
    if not headers:
        raise AuthenticationError("No valid Spotify token available")
    
    # Validate time_range
    valid_time_ranges = ["short_term", "medium_term", "long_term"]
    if time_range not in valid_time_ranges:
        logger.warning(f"Invalid time_range: {time_range}, using medium_term instead")
        time_range = "short_term"
    
    try:
        params = {
            "limit": min(limit, 50),  # Spotify API limit is 50
            "time_range": time_range
        }
        
        logger.info(f"Getting top tracks with params: {params}")
        
        response = requests.get(
            f"{SPOTIFY_API_BASE_URL}/me/top/tracks",
            headers=headers,
            params=params
        )
        
        if response.status_code != 200:
            try:
                response_data = response.json()
                error_message = response_data.get('error', {}).get('message', 'Unknown error')
            except:
                error_message = f"Status code: {response.status_code}"
                
            raise SpotifyAPIError(
                f"Failed to get top tracks: {error_message}",
                status_code=response.status_code,
                endpoint=f"{SPOTIFY_API_BASE_URL}/me/top/tracks",
                context={"time_range": time_range}
            )
            
        data = response.json()
        return data.get("items", [])
    except requests.RequestException as e:
        raise SpotifyAPIError(
            f"Network error getting top tracks: {str(e)}",
            endpoint=f"{SPOTIFY_API_BASE_URL}/me/top/tracks"
        )

@catch_exceptions
def get_recommendations(track_ids):
    """
    Get recommendations from random tracks of all artists in top-10.
    
    For each artist in the user's top tracks, this function:
    1. Gets the artist's albums
    2. Selects one random track from each album
    3. Returns up to 10 random tracks from these selections
    
    Args:
        track_ids (list): List of Spotify track IDs to use as seed
        
    Returns:
        list: List of recommended track objects or empty list if request fails
    """
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
            print(
                f"Error fetching track info: {track_response.status_code}, {track_response.text}"
            )
            continue

        # Get artist ID
        artist_id = track_response.json()["artists"][0]["id"]

        # Skip if artist already processed
        if artist_id in processed_artists:
            continue
        processed_artists.add(artist_id)

        # Get artist's albums
        artist_albums_url = f"{SPOTIFY_API_BASE_URL}/artists/{artist_id}/albums"
        albums_response = requests.get(
            artist_albums_url, headers=headers, params={"limit": 20}
        )

        if albums_response.status_code != 200:
            print(
                f"Error fetching artist albums: {albums_response.status_code}, {albums_response.text}"
            )
            continue

        # Collect tracks from albums
        for album in albums_response.json().get("items", []):
            album_tracks_url = f"{SPOTIFY_API_BASE_URL}/albums/{album['id']}/tracks"
            tracks_response = requests.get(album_tracks_url, headers=headers)

            if tracks_response.status_code == 200:
                album_tracks = tracks_response.json().get("items", [])
                # Add only one random track from album
                if album_tracks:
                    random_track = random.choice(album_tracks)
                    all_track_ids.append(random_track["id"])

    # Remove tracks that are already in user's top
    all_track_ids = [tid for tid in all_track_ids if tid not in track_ids]

    # Select random 10 tracks
    if len(all_track_ids) > 10:
        selected_track_ids = random.sample(all_track_ids, 10)
    else:
        selected_track_ids = all_track_ids

    # Get full information about selected tracks
    tracks_url = f"{SPOTIFY_API_BASE_URL}/tracks"
    params = {"ids": ",".join(selected_track_ids), "market": "US"}

    response = requests.get(tracks_url, headers=headers, params=params)

    if response.status_code != 200:
        print(
            f"Error fetching selected tracks: {response.status_code}, {response.text}"
        )
        return []

    tracks = response.json().get("tracks", [])

    # Save track IDs in session
    session["recommended_tracks"] = [track["id"] for track in tracks]

    print(f"Generated {len(tracks)} random recommendations from multiple artists")
    return tracks

@catch_exceptions
def create_playlist_with_tracks(track_uris, playlist_name="Customify Recommendations"):
    """
    Create a new playlist and add tracks to it.
    
    Args:
        track_uris (list): List of Spotify track URIs to add to the playlist
        playlist_name (str): Name for the new playlist
        
    Returns:
        bool: True if playlist was created and tracks were added successfully
    """
    headers = get_headers()
    if not headers:
        raise AuthenticationError("No valid Spotify token available")
    
    # Get user ID
    user_data = get_current_user(headers)
    if not user_data or "id" not in user_data:
        raise DataProcessingError(
            "Failed to get user ID for playlist creation",
            data_type="user_profile"
        )
    
    user_id = user_data["id"]
    
    # Create playlist
    try:
        playlist_data = {
            "name": playlist_name,
            "description": "Created with Customify - Your personalized music recommendations",
            "public": True
        }
        
        response = requests.post(
            f"{SPOTIFY_API_BASE_URL}/users/{user_id}/playlists",
            headers=headers,
            json=playlist_data
        )
        
        if response.status_code != 201:
            response_data = response.json()
            raise SpotifyAPIError(
                f"Failed to create playlist: {response_data.get('error', {}).get('message', 'Unknown error')}",
                status_code=response.status_code,
                endpoint=f"{SPOTIFY_API_BASE_URL}/users/{user_id}/playlists",
                context={"response": response_data}
            )
            
        playlist = response.json()
        playlist_id = playlist["id"]
        
        # Add tracks to playlist
        tracks_data = {
            "uris": track_uris
        }
        
        response = requests.post(
            f"{SPOTIFY_API_BASE_URL}/playlists/{playlist_id}/tracks",
            headers=headers,
            json=tracks_data
        )
        
        if response.status_code != 201:
            response_data = response.json()
            raise SpotifyAPIError(
                f"Failed to add tracks to playlist: {response_data.get('error', {}).get('message', 'Unknown error')}",
                status_code=response.status_code,
                endpoint=f"{SPOTIFY_API_BASE_URL}/playlists/{playlist_id}/tracks",
                context={"response": response_data}
            )
            
        return True
    except requests.RequestException as e:
        raise SpotifyAPIError(
            f"Network error creating playlist: {str(e)}",
            endpoint=f"{SPOTIFY_API_BASE_URL}/users/{user_id}/playlists"
        )

@catch_exceptions
def is_premium_user():
    """
    Check if the current user has a Spotify Premium subscription.
    
    Returns:
        bool: True if user has Premium, False otherwise
    """
    user_data = get_current_user()
    if not user_data:
        return False
        
    return user_data.get("product") == "premium" 