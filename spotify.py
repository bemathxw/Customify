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
    SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI, SPOTIFY_SCOPES
)

spotify_bp = Blueprint("spotify", __name__)

# Routes
@spotify_bp.route("/login")
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
    
    # Check for error
    if "error" in request.args:
        error = request.args.get("error")
        logger.error(f"Spotify auth error: {error}")
        flash(f"Authentication error: {error}", "error")
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
    
    logger.info("User logged out")
    logger.debug(f"Session after logout: {session}")
    flash("You have been logged out.", "info")
    return redirect(url_for("profile"))

@spotify_bp.route("/create-playlist", methods=["POST"])
def create_playlist():
    """
    Create a Spotify playlist with recommended tracks.
    
    This route takes track URIs from the request and creates a new
    Spotify playlist with those tracks.
    
    Returns:
        JSON response with success status and playlist information
    """
    logger.info("Processing create playlist request")
    
    try:
        # Check if user is authenticated
        if "spotify_token" not in session:
            raise AuthenticationError("Not authenticated with Spotify")
        
        # Get track URIs from request
        data = request.get_json()
        if not data or "track_uris" not in data:
            raise DataProcessingError(
                "No track URIs provided",
                data_type="request_data"
            )
        
        track_uris = data["track_uris"]
        playlist_name = data.get("playlist_name", "Customify Recommendations")
        
        if not track_uris:
            raise DataProcessingError(
                "Empty track URIs list",
                data_type="track_uris"
            )
        
        # Create playlist
        success = create_playlist_with_tracks(track_uris, playlist_name)
        
        if success:
            logger.info(f"Playlist '{playlist_name}' created successfully")
            return jsonify({
                "success": True,
                "message": "Playlist created successfully!"
            })
        else:
            raise DataProcessingError(
                "Failed to create playlist",
                data_type="playlist_creation"
            )
    except AppError as e:
        logger.error(f"Error creating playlist: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e),
            "error_id": getattr(e, "error_id", None)
        }), 400
    except Exception as e:
        logger.error(f"Unexpected error creating playlist: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "An unexpected error occurred"
        }), 500

@spotify_bp.route("/add-recommendations-to-queue", methods=["POST"])
def add_recommendations_to_queue():
    """
    Add recommended tracks to the user's Spotify queue.
    
    This route takes the recommended tracks and adds them to the user's
    Spotify playback queue.
    
    Returns:
        Redirect to profile page with success/error message
    """
    logger.info("Processing add recommendations to queue request")
    
    try:
        # Проверяем, авторизован ли пользователь
        if "spotify_token" not in session:
            logger.warning("User not authenticated for queue addition")
            flash("You need to log in to add tracks to your queue", "error")
            return redirect(url_for('profile'))
        
        # Проверяем, является ли пользователь премиум-пользователем
        if not is_premium_user():
            logger.warning("Non-premium user attempted to add to queue")
            flash("You need Spotify Premium to add tracks to your queue", "error")
            return redirect(url_for('profile'))
        
        # В реальном приложении здесь должен быть код для добавления треков в очередь
        # Для этого нужно использовать Spotify API endpoint /me/player/queue
        
        # Здесь мы просто перенаправляем на страницу профиля с сообщением
        flash("This feature is not fully implemented yet", "info")
        return redirect(url_for('profile'))
    except Exception as e:
        logger.error(f"Error adding to queue: {str(e)}", exc_info=True)
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for('profile'))
