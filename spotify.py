import os
import random
import time
import sys
from urllib.parse import urlencode

import requests
from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from loguru import logger

from errors import AppError, SpotifyAPIError, AuthenticationError, DataProcessingError, catch_exceptions
from spotify_api import (
    get_recommendations, get_top_tracks, is_premium_user, get_headers, get_current_user,
    create_playlist_with_tracks, SPOTIFY_AUTH_URL, SPOTIFY_TOKEN_URL, SPOTIFY_API_BASE_URL,
    SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI, SPOTIFY_SCOPES,
    get_similar_tracks
)

# Import profiling functions
from profiling import profile_function, track_page_view, track_user_error, track_recommendation_interaction, track_playlist_interaction

# Import caching functions
from cache import clear_cache_for_function

spotify_bp = Blueprint("spotify", __name__)

@spotify_bp.route("/top-tracks")
@profile_function
def top_tracks():
    """
    Get user's top tracks from Spotify.
    
    Returns:
        JSON response with success status and track data
    """
    logger.info("Processing top tracks request")
    
    try:
        # Check if user is authenticated
        if "spotify_token" not in session:
            raise AuthenticationError("Not authenticated with Spotify") 
        
        headers = get_headers()
        if not headers:
            raise AuthenticationError("Invalid Spotify token")
        
        # Get top tracks
        spotify_top_tracks = get_top_tracks(headers)
        
        return jsonify({
            "success": True,
            "tracks": spotify_top_tracks
        })
    except Exception as e:
        logger.error(f"Error in top tracks request: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    
    
    # Routes
@spotify_bp.route("/login")
@profile_function
def login():
    """
    Redirect user to Spotify authorization page.
    
    This route initiates the OAuth flow by redirecting the user to Spotify's
    authorization page where they can grant permission to the app.
    
    Returns:
        Redirect to Spotify authorization page
    """
    logger.info("Initiating Spotify login")
    logger.debug(f"Session before login: {session}")
    
    # Track user interaction
    track_page_view("spotify_login")
    
    # Generate state parameter for security
    state = os.urandom(16).hex()
    session["spotify_auth_state"] = state
    
    # Build authorization URL
    params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "state": state,
        "scope": " ".join(SPOTIFY_SCOPES),
        "show_dialog": True
    }
    
    auth_url = f"{SPOTIFY_AUTH_URL}?{urlencode(params)}"
    logger.info(f"Redirecting to Spotify auth URL: {auth_url}")
    
    return redirect(auth_url)

@spotify_bp.route("/callback")
@profile_function
def callback():
    """
    Handle callback from Spotify authorization.
    
    This route handles the callback from Spotify's authorization page,
    exchanges the authorization code for access and refresh tokens,
    and stores them in the session.
    
    Returns:
        Redirect to profile page or error page
    """
    logger.info("Received callback from Spotify")
    logger.debug(f"Callback request args: {request.args}")
    logger.debug(f"Session in callback: {session}")
    
    # Track user interaction
    track_page_view("spotify_callback")
    
    # Check for error
    if "error" in request.args:
        error = request.args.get("error")
        logger.error(f"Spotify auth error: {error}")
        flash(f"Authentication error: {error}", "error")
        
        # Track error
        track_user_error("auth_error", error, "spotify_callback")
        
        return redirect(url_for("profile"))
    
    # Verify state parameter
    state = request.args.get("state")
    stored_state = session.get("spotify_auth_state")
    
    if not state or state != stored_state:
        logger.warning(f"State mismatch in Spotify callback. Got: {state}, Expected: {stored_state}")
        flash("State verification failed. Please try again.", "error")
        return redirect(url_for("profile"))
    
    # Exchange code for tokens
    code = request.args.get("code")
    
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "client_id": SPOTIFY_CLIENT_ID,
        "client_secret": SPOTIFY_CLIENT_SECRET
    }
    
    try:
        response = requests.post(SPOTIFY_TOKEN_URL, data=payload)
        token_data = response.json()
        
        if response.status_code != 200:
            logger.error(f"Token exchange error: {token_data}")
            flash("Failed to get access token. Please try again.", "error")
            return redirect(url_for("profile"))
        
        # Store tokens in session
        session["spotify_token"] = token_data["access_token"]
        session["spotify_refresh_token"] = token_data["refresh_token"]
        session["spotify_token_expires_in"] = time.time() + token_data["expires_in"]
        
        # Get user profile
        headers = {"Authorization": f"Bearer {token_data['access_token']}"}
        user_data = get_current_user(headers)
        
        if user_data and "id" in user_data:
            session["user_id"] = user_data["id"]
            session["username"] = user_data.get("display_name", user_data["id"])
            logger.info(f"User authenticated: {session['username']}")
            flash(f"Welcome, {session['username']}!", "success")
        else:
            logger.warning("Failed to get user profile after authentication")
            flash("Authentication successful, but failed to get user profile.", "warning")
        
        logger.debug(f"Session after successful authentication: {session}")
        return redirect(url_for("profile"))
    except Exception as e:
        logger.error(f"Error in Spotify callback: {str(e)}", exc_info=True)
        flash("An error occurred during authentication. Please try again.", "error")
        return redirect(url_for("profile"))

@spotify_bp.route("/logout")
def logout():
    """
    Log out user by clearing Spotify-related session data.
    
    Returns:
        Redirect to profile page
    """
    logger.info("Spotify logout called")
    logger.debug(f"Session before logout: {session}")
    
    # Clear Spotify-related session data
    spotify_keys = [
        "spotify_token", 
        "spotify_refresh_token", 
        "spotify_token_expires_in",
        "spotify_auth_state",
        "user_id",
        "username",
        "top_track_ids"
    ]
    
    for key in spotify_keys:
        if key in session:
            session.pop(key)
    
    # Clear cache for user-related functions
    clear_cache_for_function("get_current_user")
    clear_cache_for_function("get_top_tracks")
    clear_cache_for_function("get_recommendations")
    
    logger.info("User logged out")
    logger.debug(f"Session after logout: {session}")
    flash("You have been logged out.", "info")
    return redirect(url_for("profile"))

@spotify_bp.route("/create-playlist", methods=["POST"])
@profile_function
def create_playlist():
    """
    Creates a new playlist and optionally adds a track to it.
    
    Returns:
        JSON with operation result
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Authentication required"}), 200
        
        # Get data from request
        data = request.json
        if not data or "name" not in data:
            return jsonify({"success": False, "error": "Playlist name not specified"}), 200
        
        name = data["name"]
        description = data.get("description", "")
        is_public = data.get("public", False)
        track_uri = data.get("track_uri", None)
        
        # Get headers with token
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Invalid token"}), 200
        
        # Get user ID
        user_response = requests.get(f"{SPOTIFY_API_BASE_URL}/me", headers=headers)
        if user_response.status_code != 200:
            return jsonify({"success": False, "error": "Failed to get user data"}), 200
        
        user_id = user_response.json()["id"]
        
        # Create playlist
        playlist_response = requests.post(
            f"{SPOTIFY_API_BASE_URL}/users/{user_id}/playlists",
            headers=headers,
            json={
                "name": name,
                "description": description,
                "public": is_public
            }
        )
        
        if playlist_response.status_code not in [200, 201]:
            error_message = "Error creating playlist"
            try:
                error_data = playlist_response.json()
                if "error" in error_data and "message" in error_data["error"]:
                    error_message = error_data["error"]["message"]
            except:
                pass
            
            logger.error(f"Error creating playlist: {playlist_response.status_code} {error_message}")
            return jsonify({"success": False, "error": error_message}), 200
        
        playlist_data = playlist_response.json()
        playlist_id = playlist_data["id"]
        
        logger.info(f"Created playlist {name} (ID: {playlist_id})")
        
        # If track URI is specified, add it to the playlist
        if track_uri:
            track_response = requests.post(
                f"{SPOTIFY_API_BASE_URL}/playlists/{playlist_id}/tracks",
                headers=headers,
                json={"uris": [track_uri]}
            )
            
            if track_response.status_code not in [200, 201]:
                logger.warning(f"Failed to add track {track_uri} to new playlist: {track_response.status_code}")
                # Return success for playlist creation, but with a warning
                return jsonify({
                    "success": True,
                    "warning": "Playlist created, but there was an error adding the track"
                })
            
            logger.info(f"Track {track_uri} added to new playlist {playlist_id}")
        
        return jsonify({
            "success": True,
            "playlist": {
                "id": playlist_id,
                "name": name,
                "external_url": playlist_data.get("external_urls", {}).get("spotify", "")
            }
        })
            
    except Exception as e:
        logger.error(f"Error creating playlist: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/add-recommendations-to-queue", methods=["POST"])
def add_recommendations_to_queue():
    """
    Adds recommended tracks from session to the playback queue.
    
    Returns:
        JSON with operation result
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Authentication required"}), 200
        
        # Get tracks from session
        tracks = session.get("recommended_tracks", [])
        
        if not tracks:
            return jsonify({"success": False, "error": "No tracks to add"}), 200
        
        # Get headers with token
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Invalid token"}), 200
        
        # Check if user is a premium subscriber (only they can manage the queue)
        if not is_premium_user():
            return jsonify({
                "success": False, 
                "error": "Adding to queue is only available for Spotify Premium users"
            }), 200
        
        # Check if there is an active device
        device_response = requests.get(f"{SPOTIFY_API_BASE_URL}/me/player/devices", headers=headers)
        if device_response.status_code != 200 or not device_response.json().get("devices"):
            return jsonify({
                "success": False,
                "error": "No active playback devices. Open Spotify on any device."
            }), 200
            
        # Add tracks to queue one by one (that's how Spotify API works)
        successful_tracks = 0
        
        for track in tracks:
            # Extract track ID from object, handling different possible formats
            track_id = None
            
            if isinstance(track, str):
                # If it's just an ID string
                track_id = track
            elif isinstance(track, dict):
                # If it's an object with fields
                track_id = track.get('id')
                if not track_id and 'uri' in track:
                    # Extract ID from URI if available
                    uri_parts = track['uri'].split(':')
                    if len(uri_parts) == 3 and uri_parts[1] == 'track':
                        track_id = uri_parts[2]
            
            if not track_id:
                logger.warning(f"Failed to extract track ID from object: {track}")
                continue
                
            # Form URI for adding to queue
            uri = f"spotify:track:{track_id}"
            
            # Add track to queue
            response = requests.post(
                f"{SPOTIFY_API_BASE_URL}/me/player/queue",
                headers=headers,
                params={"uri": uri}
            )
            
            if response.status_code == 200:
                successful_tracks += 1
                logger.info(f"Track {track_id} successfully added to queue")
            else:
                error_text = ""
                try:
                    error_text = response.json().get("error", {}).get("message", "")
                except:
                    pass
                
                logger.warning(f"Failed to add track {track_id} to queue: {response.status_code} {error_text}")
        
        # Return result
        if successful_tracks > 0:
            return jsonify({
                "success": True,
                "message": f"Added {successful_tracks} out of {len(tracks)} tracks to queue"
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to add tracks to queue. Check active device."
            })
            
    except Exception as e:
        logger.error(f"Error adding tracks to queue: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 200

# Add new route for tracking interactions from frontend
@spotify_bp.route("/track-interaction", methods=["POST"])
def track_interaction():
    """
    Endpoint for tracking user interactions from frontend.
    
    Returns:
        JSON response with confirmation
    """
    try:
        data = request.json
        
        if not data or "type" not in data:
            return jsonify({"error": "Invalid data"}), 400
            
        interaction_type = data["type"]
        
        if interaction_type == "button_click":
            from profiling import track_button_click
            track_button_click(data.get("button_id", "unknown"), data.get("page", "unknown"))
        elif interaction_type == "form_submit":
            from profiling import track_form_submit
            track_form_submit(data.get("form_id", "unknown"), 
                             data.get("form_data", {}), 
                             data.get("page", "unknown"))
        elif interaction_type == "error":
            track_user_error(data.get("error_type", "unknown"), 
                            data.get("error_message", "unknown error"), 
                            data.get("page", "unknown"))
        
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error tracking interaction: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@spotify_bp.route("/now-playing")
def now_playing():
    """
    Gets information about the current track and user's playback state.
    
    Returns:
        JSON with current playback information
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Authentication required", "is_playing": False}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Invalid token", "is_playing": False}), 200
        
        # Get full information about current playback
        response = requests.get(
            f"{SPOTIFY_API_BASE_URL}/me/player", 
            headers=headers,
            params={"additional_types": "track,episode"}
        )
        
        # If no active device (204)
        if response.status_code == 204:
            return jsonify({"success": False, "is_playing": False}), 200
        
        # If successful response
        if response.status_code == 200:
            data = response.json()
            
            # If no active track
            if not data or not data.get("item"):
                return jsonify({"success": False, "is_playing": False}), 200
            
            return jsonify({
                "success": True,
                "is_playing": data.get("is_playing", False),
                "progress_ms": data.get("progress_ms", 0),
                "item": data.get("item"),
                "device": data.get("device"),
                "shuffle_state": data.get("shuffle_state", False),
                "repeat_state": data.get("repeat_state", "off")
            }), 200
            
        # In other cases - error
        return jsonify({
            "success": False, 
            "error": f"Spotify API Error: {response.status_code}", 
            "is_playing": False
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "is_playing": False}), 200

@spotify_bp.route("/toggle-playback", methods=["POST"])
def toggle_playback():
    """
    Toggles play/pause of the current track in Spotify.
    
    Returns:
        JSON with operation result
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Authentication required"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Invalid token"}), 200
        
        # First check current state
        response = requests.get(f"{SPOTIFY_API_BASE_URL}/me/player", headers=headers)
        
        if response.status_code == 204:
            return jsonify({"success": False, "error": "No active device"}), 200
        
        if response.status_code != 200:
            return jsonify({
                "success": False,
                "error": f"Spotify API Error: {response.status_code}"
            }), 200
        
        # Determine what to do: pause or play
        player_state = response.json()
        is_playing = player_state.get("is_playing", False)
        
        if is_playing:
            # If playing - pause
            response = requests.put(f"{SPOTIFY_API_BASE_URL}/me/player/pause", headers=headers)
        else:
            # If paused - play
            response = requests.put(f"{SPOTIFY_API_BASE_URL}/me/player/play", headers=headers)
        
        if response.status_code in [204, 202, 200]:
            return jsonify({
                "success": True,
                "is_playing": not is_playing
            })
        
        return jsonify({
            "success": False,
            "error": f"Spotify API Error: {response.status_code}"
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/next-track", methods=["POST"])
def next_track():
    """
    Skips to the next track.
    
    Returns:
        JSON with operation result
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Authentication required"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Invalid token"}), 200
        
        response = requests.post(f"{SPOTIFY_API_BASE_URL}/me/player/next", headers=headers)
        
        if response.status_code in [204, 202, 200]:
            return jsonify({"success": True})
        
        return jsonify({
            "success": False,
            "error": f"Spotify API Error: {response.status_code}"
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/previous-track", methods=["POST"])
def previous_track():
    """
    Skips to the previous track.
    
    Returns:
        JSON with operation result
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Authentication required"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Invalid token"}), 200
        
        response = requests.post(f"{SPOTIFY_API_BASE_URL}/me/player/previous", headers=headers)
        
        if response.status_code in [204, 202, 200]:
            return jsonify({"success": True})
        
        return jsonify({
            "success": False,
            "error": f"Spotify API Error: {response.status_code}"
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/seek", methods=["POST"])
def seek_position():
    """
    Seeks to the specified position in the track.
    
    Returns:
        JSON with operation result
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Authentication required"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Invalid token"}), 200
        
        data = request.json
        position_ms = data.get("position_ms", 0)
        
        response = requests.put(
            f"{SPOTIFY_API_BASE_URL}/me/player/seek",
            headers=headers,
            params={"position_ms": position_ms}
        )
        
        if response.status_code in [204, 202, 200]:
            return jsonify({"success": True})
        
        return jsonify({
            "success": False,
            "error": f"Spotify API Error: {response.status_code}"
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/volume", methods=["POST"])
def set_volume():
    """
    Sets the playback volume.
    
    Returns:
        JSON with operation result
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Authentication required"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Invalid token"}), 200
        
        data = request.json
        volume_percent = data.get("volume_percent", 50)
        
        response = requests.put(
            f"{SPOTIFY_API_BASE_URL}/me/player/volume",
            headers=headers,
            params={"volume_percent": volume_percent}
        )
        
        if response.status_code in [204, 202, 200]:
            return jsonify({"success": True})
        
        return jsonify({
            "success": False,
            "error": f"Spotify API Error: {response.status_code}"
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/toggle-shuffle", methods=["POST"])
def toggle_shuffle():
    """
    Toggles shuffle mode.
    
    Returns:
        JSON with operation result
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Authentication required"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Invalid token"}), 200
        
        # Get current state
        response = requests.get(f"{SPOTIFY_API_BASE_URL}/me/player", headers=headers)
        
        if response.status_code != 200:
            return jsonify({
                "success": False,
                "error": f"Spotify API Error: {response.status_code}"
            }), 200
        
        data = response.json()
        current_state = data.get("shuffle_state", False)
        new_state = not current_state
        
        response = requests.put(
            f"{SPOTIFY_API_BASE_URL}/me/player/shuffle?state={str(new_state).lower()}",
            headers=headers
        )
        
        if response.status_code in [204, 202, 200]:
            return jsonify({
                "success": True,
                "shuffle_state": new_state
            })
        
        return jsonify({
            "success": False,
            "error": f"Spotify API Error: {response.status_code}"
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/toggle-repeat", methods=["POST"])
def toggle_repeat():
    """
    Cycles through repeat modes (off -> context -> track -> off).
    
    Returns:
        JSON with operation result
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Authentication required"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Invalid token"}), 200
        
        # Get current state
        response = requests.get(f"{SPOTIFY_API_BASE_URL}/me/player", headers=headers)
        
        if response.status_code != 200:
            return jsonify({
                "success": False,
                "error": f"Spotify API Error: {response.status_code}"
            }), 200
        
        data = response.json()
        current_state = data.get("repeat_state", "off")
        
        # Determine next state in cycle
        states = ["off", "context", "track"]
        current_index = states.index(current_state) if current_state in states else 0
        next_index = (current_index + 1) % len(states)
        new_state = states[next_index]
        
        response = requests.put(
            f"{SPOTIFY_API_BASE_URL}/me/player/repeat?state={new_state}",
            headers=headers
        )
        
        if response.status_code in [204, 202, 200]:
            return jsonify({
                "success": True,
                "repeat_state": new_state
            })
        
        return jsonify({
            "success": False,
            "error": f"Spotify API Error: {response.status_code}"
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/check-saved-track")
def check_saved_track():
    """
    Checks if a track is saved in the user's library.
    
    Returns:
        JSON with result and track status
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Authentication required"}), 200
        
        track_id = request.args.get('track_id')
        if not track_id:
            return jsonify({"success": False, "error": "Track ID not specified"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Invalid token"}), 200
        
        response = requests.get(
            f"{SPOTIFY_API_BASE_URL}/me/tracks/contains",
            headers=headers,
            params={"ids": track_id}
        )
        
        if response.status_code == 200:
            is_saved = response.json()[0] if response.json() else False
            return jsonify({"success": True, "is_saved": is_saved})
        
        return jsonify({
            "success": False,
            "error": f"Spotify API Error: {response.status_code}"
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/save-track", methods=["POST"])
def save_track():
    """
    Adds a track to the user's library.
    
    Returns:
        JSON with operation result
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Authentication required"}), 200
        
        data = request.json
        track_id = data.get('track_id')
        if not track_id:
            return jsonify({"success": False, "error": "Track ID not specified"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Invalid token"}), 200
        
        response = requests.put(
            f"{SPOTIFY_API_BASE_URL}/me/tracks",
            headers=headers,
            params={"ids": track_id}
        )
        
        if response.status_code in [200, 201]:
            return jsonify({"success": True})
        
        return jsonify({
            "success": False,
            "error": f"Spotify API Error: {response.status_code}"
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/remove-saved-track", methods=["DELETE"])
def remove_saved_track():
    """
    Removes a track from the user's library.
    
    Returns:
        JSON with operation result
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Authentication required"}), 200
        
        data = request.json
        track_id = data.get('track_id')
        if not track_id:
            return jsonify({"success": False, "error": "Track ID not specified"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Invalid token"}), 200
        
        response = requests.delete(
            f"{SPOTIFY_API_BASE_URL}/me/tracks",
            headers=headers,
            params={"ids": track_id}
        )
        
        if response.status_code in [200, 204]:
            return jsonify({"success": True})
        
        return jsonify({
            "success": False,
            "error": f"Spotify API Error: {response.status_code}"
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/user-playlists")
def user_playlists():
    """
    Gets the list of user's playlists.
    
    Returns:
        JSON with playlist list
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Authentication required"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Invalid token"}), 200
        
        response = requests.get(
            f"{SPOTIFY_API_BASE_URL}/me/playlists",
            headers=headers,
            params={"limit": 50}
        )
        
        if response.status_code == 200:
            playlists_data = response.json()
            return jsonify({
                "success": True, 
                "playlists": playlists_data.get("items", [])
            })
        
        return jsonify({
            "success": False,
            "error": f"Spotify API Error: {response.status_code}"
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/add-to-playlist", methods=["POST"])
def add_to_playlist():
    """
    Adds a track to a playlist.
    
    Returns:
        JSON with operation result
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Authentication required"}), 200
        
        data = request.json
        playlist_id = data.get('playlist_id')
        track_uri = data.get('track_uri')
        
        if not playlist_id or not track_uri:
            return jsonify({"success": False, "error": "Playlist ID or track URI not specified"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Invalid token"}), 200
        
        response = requests.post(
            f"{SPOTIFY_API_BASE_URL}/playlists/{playlist_id}/tracks",
            headers=headers,
            json={"uris": [track_uri]}
        )
        
        if response.status_code in [201, 200]:
            return jsonify({"success": True})
        
        return jsonify({
            "success": False,
            "error": f"Spotify API Error: {response.status_code}"
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/play-track", methods=["POST"])
def play_track():
    """
    Plays the specified track in Spotify.
    
    Returns:
        JSON with operation result
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Authentication required"}), 200
        
        data = request.json
        uri = data.get('uri')
        
        if not uri:
            return jsonify({"success": False, "error": "Track URI not specified"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Invalid token"}), 200
        
        # Forming request with track URI
        payload = {
            "uris": [uri] if ":" in uri else None,
            "context_uri": uri if ":" not in uri else None
        }
        
        # Remove None values
        payload = {k: v for k, v in payload.items() if v is not None}
        
        # Play the track
        response = requests.put(
            f"{SPOTIFY_API_BASE_URL}/me/player/play", 
            headers=headers,
            json=payload
        )
        
        if response.status_code in [204, 202, 200]:
            return jsonify({"success": True})
        
        error_info = ""
        try:
            error_data = response.json()
            error_info = f": {error_data.get('error', {}).get('message', '')}"
        except:
            pass
            
        return jsonify({
            "success": False,
            "error": f"Spotify API Error: {response.status_code}{error_info}"
        }), 200
        
    except Exception as e:
        logger.error(f"Error playing track: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/get-similar-tracks", methods=["GET"])
def get_similar_tracks_endpoint():
    """
    Endpoint for getting similar tracks by ID.
    
    Query parameters:
        track_id (str): Spotify track ID
    
    Returns:
        JSON with similar tracks or error message
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Authentication required"}), 200
            
        track_id = request.args.get('track_id')
        if not track_id:
            return jsonify({"success": False, "error": "Track ID not specified"}), 200
            
        # Get similar tracks
        result = get_similar_tracks(track_id)
        
        # Return result
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error getting similar tracks: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/save-tracks-to-session", methods=["POST"])
def save_tracks_to_session():
    """
    Saves list of tracks in user session.
    
    Returns:
        JSON response with confirmation
    """
    try:
        session["recommended_tracks"] = None
        data = request.json
        if not data or "tracks" not in data:
            return jsonify({"success": False, "error": "No tracks provided"}), 200
            
        tracks = data["tracks"]
        session["recommended_tracks"] = tracks
        logger.info(f"Saved {len(tracks)} tracks to session")
        
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error saving tracks to session: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/get-session-tracks")
def get_session_tracks():
    """
    Returns tracks from session in JSON format
    
    Returns:
        JSON with tracks from session
    """
    try:
        tracks = session.get("recommended_tracks", [])
        return jsonify({"success": True, "tracks": tracks})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@spotify_bp.route("/get-my-playlists")
def get_my_playlists():
    """
    Gets the list of user's playlists.
    
    Returns:
        JSON with user's playlists
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Authentication required"}), 200
        
        # Get headers with token
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Invalid token"}), 200
        
        # Get user's playlists
        playlists = []
        next_url = f"{SPOTIFY_API_BASE_URL}/me/playlists?limit=50"
        
        while next_url:
            response = requests.get(next_url, headers=headers)
            
            if response.status_code != 200:
                return jsonify({"success": False, "error": f"Spotify API Error: {response.status_code}"}), 200
                
            data = response.json()
            playlists.extend(data["items"])
            next_url = data.get("next")
        
        logger.info(f"Retrieved {len(playlists)} user playlists")
        return jsonify({"success": True, "playlists": playlists})
            
    except Exception as e:
        logger.error(f"Error getting playlists: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/add-track-to-playlist", methods=["POST"])
def add_track_to_playlist():
    """
    Adds a track to the specified playlist.
    
    Returns:
        JSON with operation result
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Authentication required"}), 200
        
        # Get data from request
        data = request.json
        if not data or "playlist_id" not in data or "track_uri" not in data:
            return jsonify({"success": False, "error": "Playlist ID or track URI not specified"}), 200
        
        playlist_id = data["playlist_id"]
        track_uri = data["track_uri"]
        
        # Get headers with token
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Invalid token"}), 200
        
        # Add track to playlist
        response = requests.post(
            f"{SPOTIFY_API_BASE_URL}/playlists/{playlist_id}/tracks",
            headers=headers,
            json={"uris": [track_uri]}
        )
        
        if response.status_code in [200, 201]:
            logger.info(f"Track {track_uri} successfully added to playlist {playlist_id}")
            return jsonify({"success": True})
        else:
            error_message = "Error adding track to playlist"
            try:
                error_data = response.json()
                if "error" in error_data and "message" in error_data["error"]:
                    error_message = error_data["error"]["message"]
            except:
                pass
            
            logger.error(f"Error adding track to playlist: {response.status_code} {error_message}")
            return jsonify({"success": False, "error": error_message}), 200
            
    except Exception as e:
        logger.error(f"Error adding track to playlist: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/add-all-tracks-to-playlist", methods=["POST"])
def add_all_tracks_to_playlist():
    """
    Adds all tracks from session to the specified playlist.
    
    Returns:
        JSON with operation result
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Authentication required"}), 200
        
        # Get data from request
        data = request.json
        if not data or "playlist_id" not in data:
            return jsonify({"success": False, "error": "Playlist ID not specified"}), 200
        
        playlist_id = data["playlist_id"]
        
        # Get tracks from session
        tracks = session.get("recommended_tracks", [])
        
        if not tracks:
            return jsonify({"success": False, "error": "No tracks to add"}), 200
        
        # Get headers with token
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Invalid token"}), 200
        
        # Convert tracks to URI format
        track_uris = []
        for track in tracks:
            track_id = None
            
            if isinstance(track, str):
                # If it's just an ID string
                track_id = track
            elif isinstance(track, dict):
                # If it's an object with fields
                track_id = track.get('id')
                if not track_id and 'uri' in track:
                    # Extract ID from URI if available
                    uri_parts = track['uri'].split(':')
                    if len(uri_parts) == 3 and uri_parts[1] == 'track':
                        track_id = uri_parts[2]
            
            if track_id:
                track_uris.append(f"spotify:track:{track_id}")
        
        if not track_uris:
            return jsonify({"success": False, "error": "Failed to extract track IDs"}), 200
        
        # Add tracks to playlist in groups of 100 (Spotify API limit)
        added_count = 0
        for i in range(0, len(track_uris), 100):
            batch = track_uris[i:i+100]
            
            response = requests.post(
                f"{SPOTIFY_API_BASE_URL}/playlists/{playlist_id}/tracks",
                headers=headers,
                json={"uris": batch}
            )
            
            if response.status_code in [200, 201]:
                added_count += len(batch)
            else:
                error_message = "Error adding tracks to playlist"
                try:
                    error_data = response.json()
                    if "error" in error_data and "message" in error_data["error"]:
                        error_message = error_data["error"]["message"]
                except:
                    pass
                
                logger.error(f"Error adding tracks to playlist: {response.status_code} {error_message}")
                return jsonify({"success": False, "error": error_message}), 200
        
        logger.info(f"Added {added_count} tracks to playlist {playlist_id}")
        return jsonify({"success": True, "added_count": added_count})
            
    except Exception as e:
        logger.error(f"Error adding tracks to playlist: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/create-playlist-with-all-tracks", methods=["POST"])
def create_playlist_with_all_tracks():
    """
    Creates a new playlist and adds all tracks from session to it.
    
    Returns:
        JSON with operation result
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Authentication required"}), 200
        
        # Get data from request
        data = request.json
        if not data or "name" not in data:
            return jsonify({"success": False, "error": "Playlist name not specified"}), 200
        
        name = data["name"]
        description = data.get("description", "")
        is_public = data.get("public", False)
        
        # Get tracks from session
        tracks = session.get("recommended_tracks", [])
        
        if not tracks:
            return jsonify({"success": False, "error": "No tracks to add"}), 200
        
        # Get headers with token
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Invalid token"}), 200
        
        # Get user ID
        user_response = requests.get(f"{SPOTIFY_API_BASE_URL}/me", headers=headers)
        if user_response.status_code != 200:
            return jsonify({"success": False, "error": "Failed to get user data"}), 200
        
        user_id = user_response.json()["id"]
        
        # Create playlist
        playlist_response = requests.post(
            f"{SPOTIFY_API_BASE_URL}/users/{user_id}/playlists",
            headers=headers,
            json={
                "name": name,
                "description": description,
                "public": is_public
            }
        )
        
        if playlist_response.status_code not in [200, 201]:
            error_message = "Error creating playlist"
            try:
                error_data = playlist_response.json()
                if "error" in error_data and "message" in error_data["error"]:
                    error_message = error_data["error"]["message"]
            except:
                pass
            
            logger.error(f"Error creating playlist: {playlist_response.status_code} {error_message}")
            return jsonify({"success": False, "error": error_message}), 200
        
        playlist_data = playlist_response.json()
        playlist_id = playlist_data["id"]
        
        logger.info(f"Created playlist {name} (ID: {playlist_id})")
        
        # Convert tracks to URI format
        track_uris = []
        for track in tracks:
            track_id = None
            
            if isinstance(track, str):
                # If it's just an ID string
                track_id = track
            elif isinstance(track, dict):
                # If it's an object with fields
                track_id = track.get('id')
                if not track_id and 'uri' in track:
                    # Extract ID from URI if available
                    uri_parts = track['uri'].split(':')
                    if len(uri_parts) == 3 and uri_parts[1] == 'track':
                        track_id = uri_parts[2]
            
            if track_id:
                track_uris.append(f"spotify:track:{track_id}")
        
        # Add tracks to playlist in groups of 100 (Spotify API limit)
        added_count = 0
        for i in range(0, len(track_uris), 100):
            batch = track_uris[i:i+100]
            
            response = requests.post(
                f"{SPOTIFY_API_BASE_URL}/playlists/{playlist_id}/tracks",
                headers=headers,
                json={"uris": batch}
            )
            
            if response.status_code in [200, 201]:
                added_count += len(batch)
            else:
                logger.warning(f"Error adding tracks to new playlist: {response.status_code}")
        
        logger.info(f"Added {added_count} tracks to new playlist {playlist_id}")
        
        return jsonify({
            "success": True,
            "added_count": added_count,
            "playlist": {
                "id": playlist_id,
                "name": name,
                "external_url": playlist_data.get("external_urls", {}).get("spotify", "")
            }
        })
            
    except Exception as e:
        logger.error(f"Error creating playlist: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 200
    
@spotify_bp.route('/search-tracks', methods=['GET'])
def search_tracks():
    """Search tracks by name"""
    try:
        # Get query parameter
        query = request.args.get('q')
        if not query:
            return jsonify({
                'success': False,
                'error': 'Search parameter not specified'
            })
        
        # Get authorization headers
        headers = get_headers()
        if not headers:
            return jsonify({
                'success': False,
                'error': 'Authorization error'
            })
        
        # Execute request to Spotify API
        response = requests.get(
            'https://api.spotify.com/v1/search',
            headers=headers,
            params={
                'q': query,
                'type': 'track',
                'limit': 10
            }
        )
        
        # Check response
        if response.status_code != 200:
            return jsonify({
                'success': False,
                'error': f'Spotify API Error: {response.status_code}'
            })
        
        # Get results
        data = response.json()
        tracks = data.get('tracks', {}).get('items', [])
        
        return jsonify({
            'success': True,
            'tracks': tracks
        })
    
    except Exception as e:
        logger.error(f"Error searching tracks: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        })