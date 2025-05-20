import os
import time
import requests
from flask import session
from loguru import logger
import random
import logging
import traceback
from flask import current_app

from errors import AppError, SpotifyAPIError, AuthenticationError, DataProcessingError, catch_exceptions
import dotenv

dotenv.load_dotenv()

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
    "playlist-modify-private",
    "user-read-currently-playing",
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-library-modify",
    "user-library-read"
]

# Skiley API constants
SKILEY_API_URL = "https://api.skiley.net/track/similar"
SKILEY_AUTH_TOKEN = os.getenv("SKILEY_AUTH_TOKEN")

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
    # Check if token exists in session
    if 'spotify_token' not in session:
        logger.warning("No Spotify token in session")
        return None
    
    # Check if token has expired
    if 'spotify_token_expires_in' in session and time.time() > session['spotify_token_expires_in']:
        logger.info("Spotify token expired, refreshing")
        
        # Check if refresh token exists
        if 'spotify_refresh_token' not in session:
            logger.warning("No refresh token available")
            return None
        
        # Refresh token
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
                # Clear session as token is invalid
                session.pop('spotify_token', None)
                session.pop('spotify_token_expires_in', None)
                return None
                
            token_data = response.json()
            
            # Update token in session
            session['spotify_token'] = token_data['access_token']
            session['spotify_token_expires_in'] = time.time() + token_data['expires_in']
            
            # If response contains new refresh token, update it
            if 'refresh_token' in token_data:
                session['spotify_refresh_token'] = token_data['refresh_token']
                
            logger.info("Successfully refreshed Spotify token")
        except Exception as e:
            logger.error(f"Error refreshing token: {str(e)}")
            return None
    
    # Return headers with token
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
def get_recommendations():
    """
    Gets recommendations based on the first track from user's top 10.
    
    Returns:
        dict: Dictionary with success flag and list of recommended tracks
    """
    try:
        logger.info("Starting to get recommendations")
        
        # 1. Get Spotify access token
        token = get_auth_token()
        if not token:
            logger.error("Failed to get Spotify token")
            return {"success": False, "error": "Unable to get Spotify access token"}
        
        # 2. Get user's top tracks
        top_tracks = get_user_top_tracks(token)
        if not top_tracks or "items" not in top_tracks or not top_tracks["items"]:
            logger.warning("User's top tracks not found or incorrect API response")
            return {"success": False, "error": "Failed to get user's top tracks"}
        
        # 3. Take the first track from the top
        first_track = top_tracks["items"][0]
        track_id = first_track["id"]
        logger.info(f"Using track for recommendations: {first_track['name']} (ID: {track_id})")
        
        # 4. Get recommendations from Skiley API
        skiley_tracks = get_skiley_recommendations(track_id)
        if not skiley_tracks:
            logger.warning("No recommendations received from Skiley API")
            return {"success": False, "error": "Failed to get recommendations from Skiley"}
        
        # 5. Convert to Spotify API format
        formatted_tracks = format_skiley_tracks(skiley_tracks)
        logger.info(f"Generated {len(formatted_tracks)} recommendations")
        
        return {"success": True, "tracks": formatted_tracks}
        
    except Exception as e:
        logger.error(f"Error getting recommendations: {str(e)}")
        logger.error(traceback.format_exc())
        return {"success": False, "error": str(e)}

def get_auth_token():
    """Gets current Spotify access token from session or database"""
    # This implementation depends on how you store tokens
    # Here it's assumed that you have a function to get the token
    # For example, from session or database
    
    # Example:
    if 'spotify_token' in session:
        return session['spotify_token']
    return None

def get_user_top_tracks(token, limit=10, time_range="short_term"):
    """
    Gets user's top tracks via Spotify API
    
    Args:
        token (str): Spotify access token
        limit (int): Number of tracks (maximum 50)
        time_range (str): Time period (short_term, medium_term, long_term)
    
    Returns:
        dict: API response with top tracks or None on error
    """
    try:
        url = f"{SPOTIFY_API_BASE_URL}/me/top/tracks"
        headers = {"Authorization": f"Bearer {token}"}
        params = {"limit": limit, "time_range": time_range}
        
        logger.info(f"Requesting top tracks: {url} with parameters {params}")
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code != 200:
            logger.error(f"Spotify API error: {response.status_code}, {response.text}")
            return None
            
        return response.json()
        
    except Exception as e:
        logger.error(f"Error getting top tracks: {str(e)}")
        return None

def get_skiley_recommendations(track_id, limit=10):
    """
    Gets recommendations from Skiley API
    
    Args:
        track_id (str): Spotify track ID
        limit (int): Number of recommendations
    
    Returns:
        list: List of recommended tracks or None on error
    """
    try:
        url = f"{SKILEY_API_URL}?trackId={track_id}&upToTracks={limit}"
        
        headers = {
            'accept': '*/*',
            'content-type': 'application/json',
            'x-skiley-client-name': 'skiley-web-user',
            'x-skiley-client-version': 'v4.2.860',
            'x-skiley-platform-name': 'web',
            'origin': 'https://skiley.net',
            'referer': 'https://skiley.net/'
        }
        
        cookies = {'authToken': SKILEY_AUTH_TOKEN}
        
        logger.info(f"Request to Skiley API: {url}")
        response = requests.get(url, headers=headers, cookies=cookies)
        
        if response.status_code != 200:
            logger.error(f"Skiley API error: {response.status_code}, {response.text}")
            return None
        
        # Output response for debugging
        logger.info(f"Response from Skiley API: {response.text[:200]}...")
        
        # Try different possible data structures
        data = response.json()
        
        # Check if response is a dictionary with 'tracks' key
        if isinstance(data, dict) and 'tracks' in data:
            tracks = data['tracks']
        # Check if response is a list directly
        elif isinstance(data, list):
            tracks = data
        else:
            # If no structure matches, log and return empty list
            logger.error(f"Unknown data format from Skiley API: {type(data)}")
            logger.error(f"Content: {data}")
            return []
        
        logger.info(f"Received {len(tracks)} tracks from Skiley API")
        return tracks
        
    except Exception as e:
        logger.error(f"Error requesting Skiley API: {str(e)}")
        logger.error(traceback.format_exc())
        return None

def format_skiley_tracks(skiley_tracks):
    """
    Converts tracks from Skiley API format to frontend-compatible format
    
    Args:
        skiley_tracks (list): List of tracks from Skiley API
    
    Returns:
        list: List of tracks in display format
    """
    formatted_tracks = []
    
    for track in skiley_tracks:
        try:
            logger.info(f"Processing track: {track}")
            
            # Check that track is a dictionary
            if not isinstance(track, dict):
                logger.warning(f"Skipping track: not a dictionary: {type(track)}")
                continue
                
            # Format cover (with type checking)
            images = []
            artworks = track.get("artworks")
            
            if isinstance(artworks, dict):
                # If artworks is a dictionary, process as dictionary
                if artworks.get("large"):
                    images.append({"url": artworks.get("large"), "height": 640, "width": 640})
                if artworks.get("default"):
                    images.append({"url": artworks.get("default"), "height": 300, "width": 300})
            elif isinstance(artworks, str):
                # If artworks is a string, use it as URL
                images.append({"url": artworks, "height": 300, "width": 300})
            
            # If no images, add placeholder
            if not images:
                images.append({"url": "/static/images/album-placeholder.png", "height": 300, "width": 300})
            
            # Format artists
            artist_name = track.get("artistName", "Unknown artist")
            artists = [{
                "name": artist_name,
                "external_urls": {"spotify": f"https://open.spotify.com/artist/unknown"}
            }]
            
            # Format album
            album = {
                "name": track.get("albumName", "Unknown album"),
                "images": images
            }
            
            # Format track
            formatted_track = {
                "id": track.get("id", ""),
                "name": track.get("name", "Unknown track"),
                "uri": track.get("uri", f"spotify:track:{track.get('id', '')}"),
                "external_urls": {"spotify": track.get("url", f"https://open.spotify.com/track/{track.get('id', '')}")},
                "artists": artists,
                "album": album
            }
            
            formatted_tracks.append(formatted_track)
            logger.info(f"Track successfully processed: {formatted_track['name']}")
            
        except Exception as e:
            logger.error(f"Error processing track: {str(e)}")
            logger.error(f"Original track data: {track}")
            continue
    
    return formatted_tracks

@catch_exceptions
def get_recommendations_v1(track_ids):
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

@catch_exceptions
def get_similar_tracks(track_id):
    """
    Gets similar tracks for a specific track via Skiley API.
    
    Args:
        track_id (str): Spotify track ID for which similar tracks are needed
    
    Returns:
        dict: Dictionary with success flag and list of similar tracks
    """
    try:
        logger.info(f"Starting to get similar tracks for ID: {track_id}")
        
        if not track_id:
            logger.error("No track ID specified for finding similar tracks")
            return {"success": False, "error": "No track ID specified"}
        
        # 1. Get Spotify access token for verification
        token = get_auth_token()
        if not token:
            logger.error("Failed to get Spotify token")
            return {"success": False, "error": "Unable to get Spotify access token"}
        
        # 2. Get recommendations from Skiley API
        skiley_tracks = get_skiley_recommendations(track_id)
        if not skiley_tracks:
            logger.warning(f"No recommendations received from Skiley API for track {track_id}")
            return {"success": False, "error": "Failed to get similar tracks"}
        
        # 3. Convert to Spotify API format
        formatted_tracks = format_skiley_tracks(skiley_tracks)
        logger.info(f"Generated {len(formatted_tracks)} similar tracks")
        
        return {"success": True, "tracks": formatted_tracks}
        
    except Exception as e:
        logger.error(f"Error getting similar tracks: {str(e)}")
        logger.error(traceback.format_exc())
        return {"success": False, "error": str(e)}

@catch_exceptions
def get_spotify_user_profile():
    """
    Gets detailed information about the Spotify user profile.
    
    Returns:
        dict: Dictionary with user profile data or empty dictionary in case of error
    """
    try:
        logger.info("Getting Spotify user profile")
        
        # Get headers with authorization token
        headers = get_headers()
        if not headers:
            logger.error("Failed to get authorization token")
            return {}
        
        # Get user data using existing function
        user_data = get_current_user(headers)
        
        if not user_data:
            logger.error("Failed to get user data")
            return {}
        
        # Check for avatar
        if not user_data.get('images') or len(user_data['images']) == 0:
            logger.info("User has no avatar, using default image")
            # Profile without avatar, but all other data exists
        else:
            logger.info(f"User avatar found: {user_data['images'][0].get('url', 'URL not found')}")
        
        # Check for username
        if not user_data.get('display_name'):
            logger.warning("Username not found, using user ID")
            user_data['display_name'] = user_data.get('id', 'Spotify User')
        
        logger.info(f"User profile successfully retrieved: {user_data['display_name']}")
        return user_data
        
    except Exception as e:
        logger.error(f"Error getting user profile: {str(e)}")
        logger.error(traceback.format_exc())
        return {} 