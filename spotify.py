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

# Импортируем функции профилирования
from profiling import profile_function, track_page_view, track_user_error, track_recommendation_interaction, track_playlist_interaction

# Импортируем функции кеширования
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
    
    # Отслеживаем взаимодействие пользователя
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
    
    # Отслеживаем взаимодействие пользователя
    track_page_view("spotify_callback")
    
    # Check for error
    if "error" in request.args:
        error = request.args.get("error")
        logger.error(f"Spotify auth error: {error}")
        flash(f"Authentication error: {error}", "error")
        
        # Отслеживаем ошибку
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
    
    # Очищаємо кеш для функцій, пов'язаних з користувачем
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
    Создает новый плейлист и опционально добавляет в него трек.
    
    Returns:
        JSON с результатом операции
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Требуется авторизация"}), 200
        
        # Получаем данные из запроса
        data = request.json
        if not data or "name" not in data:
            return jsonify({"success": False, "error": "Не указано название плейлиста"}), 200
        
        name = data["name"]
        description = data.get("description", "")
        is_public = data.get("public", False)
        track_uri = data.get("track_uri", None)
        
        # Получаем заголовки с токеном
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Недействительный токен"}), 200
        
        # Получаем ID пользователя
        user_response = requests.get(f"{SPOTIFY_API_BASE_URL}/me", headers=headers)
        if user_response.status_code != 200:
            return jsonify({"success": False, "error": "Не удалось получить данные пользователя"}), 200
        
        user_id = user_response.json()["id"]
        
        # Создаем плейлист
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
            error_message = "Ошибка при создании плейлиста"
            try:
                error_data = playlist_response.json()
                if "error" in error_data and "message" in error_data["error"]:
                    error_message = error_data["error"]["message"]
            except:
                pass
            
            logger.error(f"Ошибка при создании плейлиста: {playlist_response.status_code} {error_message}")
            return jsonify({"success": False, "error": error_message}), 200
        
        playlist_data = playlist_response.json()
        playlist_id = playlist_data["id"]
        
        logger.info(f"Создан плейлист {name} (ID: {playlist_id})")
        
        # Если указан URI трека, добавляем его в плейлист
        if track_uri:
            track_response = requests.post(
                f"{SPOTIFY_API_BASE_URL}/playlists/{playlist_id}/tracks",
                headers=headers,
                json={"uris": [track_uri]}
            )
            
            if track_response.status_code not in [200, 201]:
                logger.warning(f"Не удалось добавить трек {track_uri} в новый плейлист: {track_response.status_code}")
                # Возвращаем успех создания плейлиста, но с предупреждением
                return jsonify({
                    "success": True,
                    "warning": "Плейлист создан, но возникла ошибка при добавлении трека"
                })
            
            logger.info(f"Трек {track_uri} добавлен в новый плейлист {playlist_id}")
        
        return jsonify({
            "success": True,
            "playlist": {
                "id": playlist_id,
                "name": name,
                "external_url": playlist_data.get("external_urls", {}).get("spotify", "")
            }
        })
            
    except Exception as e:
        logger.error(f"Ошибка при создании плейлиста: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/add-recommendations-to-queue", methods=["POST"])
def add_recommendations_to_queue():
    """
    Добавляет рекомендуемые треки из сессии в очередь воспроизведения.
    
    Returns:
        JSON с результатом операции
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Требуется авторизация"}), 200
        
        # Получаем треки из сессии
        tracks = session.get("recommended_tracks", [])
        
        if not tracks:
            return jsonify({"success": False, "error": "Нет треков для добавления"}), 200
        
        # Получаем заголовки с токеном
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Недействительный токен"}), 200
        
        # Проверяем, является ли пользователь премиум-подписчиком (только они могут управлять очередью)
        if not is_premium_user():
            return jsonify({
                "success": False, 
                "error": "Добавление в очередь доступно только для пользователей Spotify Premium"
            }), 200
        
        # Проверяем есть ли активное устройство
        device_response = requests.get(f"{SPOTIFY_API_BASE_URL}/me/player/devices", headers=headers)
        if device_response.status_code != 200 or not device_response.json().get("devices"):
            return jsonify({
                "success": False,
                "error": "Нет активных устройств воспроизведения. Откройте Spotify на любом устройстве."
            }), 200
            
        # Добавляем треки в очередь по одному (так работает API Spotify)
        successful_tracks = 0
        
        for track in tracks:
            # Извлекаем ID трека из объекта, обрабатывая разные возможные форматы
            track_id = None
            
            if isinstance(track, str):
                # Если это просто строка ID
                track_id = track
            elif isinstance(track, dict):
                # Если это объект с полями
                track_id = track.get('id')
                if not track_id and 'uri' in track:
                    # Извлекаем ID из URI если есть
                    uri_parts = track['uri'].split(':')
                    if len(uri_parts) == 3 and uri_parts[1] == 'track':
                        track_id = uri_parts[2]
            
            if not track_id:
                logger.warning(f"Не удалось извлечь ID трека из объекта: {track}")
                continue
                
            # Формируем URI для добавления в очередь
            uri = f"spotify:track:{track_id}"
            
            # Добавляем трек в очередь
            response = requests.post(
                f"{SPOTIFY_API_BASE_URL}/me/player/queue",
                headers=headers,
                params={"uri": uri}
            )
            
            if response.status_code == 200:
                successful_tracks += 1
                logger.info(f"Трек {track_id} успешно добавлен в очередь")
            else:
                error_text = ""
                try:
                    error_text = response.json().get("error", {}).get("message", "")
                except:
                    pass
                
                logger.warning(f"Не удалось добавить трек {track_id} в очередь: {response.status_code} {error_text}")
        
        # Возвращаем результат
        if successful_tracks > 0:
            return jsonify({
                "success": True,
                "message": f"Добавлено {successful_tracks} из {len(tracks)} треков в очередь"
            })
        else:
            return jsonify({
                "success": False,
                "error": "Не удалось добавить треки в очередь. Проверьте активное устройство."
            })
            
    except Exception as e:
        logger.error(f"Ошибка при добавлении треков в очередь: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 200

# Добавляем новый маршрут для отслеживания взаимодействий с фронтенда
@spotify_bp.route("/track-interaction", methods=["POST"])
def track_interaction():
    """
    Endpoint для отслеживания взаимодействий пользователя с фронтенда.
    
    Returns:
        JSON response с подтверждением
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
    Получает информацию о текущем треке и состоянии воспроизведения пользователя.
    
    Returns:
        JSON с информацией о текущем воспроизведении
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Требуется авторизация", "is_playing": False}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Недействительный токен", "is_playing": False}), 200
        
        # Получаем полную информацию о текущем воспроизведении
        response = requests.get(
            f"{SPOTIFY_API_BASE_URL}/me/player", 
            headers=headers,
            params={"additional_types": "track,episode"}
        )
        
        # Если нет активного устройства (204)
        if response.status_code == 204:
            return jsonify({"success": False, "is_playing": False}), 200
        
        # Если успешный ответ
        if response.status_code == 200:
            data = response.json()
            
            # Если нет активного трека
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
            
        # В других случаях - ошибка
        return jsonify({
            "success": False, 
            "error": f"Ошибка API Spotify: {response.status_code}", 
            "is_playing": False
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "is_playing": False}), 200

@spotify_bp.route("/toggle-playback", methods=["POST"])
def toggle_playback():
    """
    Переключает воспроизведение/паузу текущего трека в Spotify.
    
    Returns:
        JSON с результатом операции
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Требуется авторизация"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Недействительный токен"}), 200
        
        # Сначала проверяем текущее состояние
        response = requests.get(f"{SPOTIFY_API_BASE_URL}/me/player", headers=headers)
        
        if response.status_code == 204:
            return jsonify({"success": False, "error": "Нет активного устройства"}), 200
        
        if response.status_code != 200:
            return jsonify({
                "success": False,
                "error": f"Ошибка API Spotify: {response.status_code}"
            }), 200
        
        # Определяем, что делать: пауза или воспроизведение
        player_state = response.json()
        is_playing = player_state.get("is_playing", False)
        
        if is_playing:
            # Если играет - ставим на паузу
            response = requests.put(f"{SPOTIFY_API_BASE_URL}/me/player/pause", headers=headers)
        else:
            # Если на паузе - воспроизводим
            response = requests.put(f"{SPOTIFY_API_BASE_URL}/me/player/play", headers=headers)
        
        if response.status_code in [204, 202, 200]:
            return jsonify({
                "success": True,
                "is_playing": not is_playing
            })
        
        return jsonify({
            "success": False,
            "error": f"Ошибка API Spotify: {response.status_code}"
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/next-track", methods=["POST"])
def next_track():
    """
    Переключает на следующий трек.
    
    Returns:
        JSON с результатом операции
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Требуется авторизация"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Недействительный токен"}), 200
        
        response = requests.post(f"{SPOTIFY_API_BASE_URL}/me/player/next", headers=headers)
        
        if response.status_code in [204, 202, 200]:
            return jsonify({"success": True})
        
        return jsonify({
            "success": False,
            "error": f"Ошибка API Spotify: {response.status_code}"
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/previous-track", methods=["POST"])
def previous_track():
    """
    Переключает на предыдущий трек.
    
    Returns:
        JSON с результатом операции
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Требуется авторизация"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Недействительный токен"}), 200
        
        response = requests.post(f"{SPOTIFY_API_BASE_URL}/me/player/previous", headers=headers)
        
        if response.status_code in [204, 202, 200]:
            return jsonify({"success": True})
        
        return jsonify({
            "success": False,
            "error": f"Ошибка API Spotify: {response.status_code}"
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/seek", methods=["POST"])
def seek_position():
    """
    Перематывает трек на указанную позицию.
    
    Returns:
        JSON с результатом операции
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Требуется авторизация"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Недействительный токен"}), 200
        
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
            "error": f"Ошибка API Spotify: {response.status_code}"
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/volume", methods=["POST"])
def set_volume():
    """
    Устанавливает громкость воспроизведения.
    
    Returns:
        JSON с результатом операции
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Требуется авторизация"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Недействительный токен"}), 200
        
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
            "error": f"Ошибка API Spotify: {response.status_code}"
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/toggle-shuffle", methods=["POST"])
def toggle_shuffle():
    """
    Переключает режим перемешивания.
    
    Returns:
        JSON с результатом операции
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Требуется авторизация"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Недействительный токен"}), 200
        
        # Получаем текущее состояние
        response = requests.get(f"{SPOTIFY_API_BASE_URL}/me/player", headers=headers)
        
        if response.status_code != 200:
            return jsonify({
                "success": False,
                "error": f"Ошибка API Spotify: {response.status_code}"
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
            "error": f"Ошибка API Spotify: {response.status_code}"
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/toggle-repeat", methods=["POST"])
def toggle_repeat():
    """
    Циклически переключает режим повтора (off -> context -> track -> off).
    
    Returns:
        JSON с результатом операции
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Требуется авторизация"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Недействительный токен"}), 200
        
        # Получаем текущее состояние
        response = requests.get(f"{SPOTIFY_API_BASE_URL}/me/player", headers=headers)
        
        if response.status_code != 200:
            return jsonify({
                "success": False,
                "error": f"Ошибка API Spotify: {response.status_code}"
            }), 200
        
        data = response.json()
        current_state = data.get("repeat_state", "off")
        
        # Определяем следующее состояние в цикле
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
            "error": f"Ошибка API Spotify: {response.status_code}"
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/check-saved-track")
def check_saved_track():
    """
    Проверяет, сохранен ли трек в библиотеке пользователя.
    
    Returns:
        JSON с результатом и статусом трека
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Требуется авторизация"}), 200
        
        track_id = request.args.get('track_id')
        if not track_id:
            return jsonify({"success": False, "error": "Не указан ID трека"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Недействительный токен"}), 200
        
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
            "error": f"Ошибка API Spotify: {response.status_code}"
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/save-track", methods=["POST"])
def save_track():
    """
    Добавляет трек в библиотеку пользователя.
    
    Returns:
        JSON с результатом операции
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Требуется авторизация"}), 200
        
        data = request.json
        track_id = data.get('track_id')
        if not track_id:
            return jsonify({"success": False, "error": "Не указан ID трека"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Недействительный токен"}), 200
        
        response = requests.put(
            f"{SPOTIFY_API_BASE_URL}/me/tracks",
            headers=headers,
            params={"ids": track_id}
        )
        
        if response.status_code in [200, 201]:
            return jsonify({"success": True})
        
        return jsonify({
            "success": False,
            "error": f"Ошибка API Spotify: {response.status_code}"
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/remove-saved-track", methods=["DELETE"])
def remove_saved_track():
    """
    Удаляет трек из библиотеки пользователя.
    
    Returns:
        JSON с результатом операции
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Требуется авторизация"}), 200
        
        data = request.json
        track_id = data.get('track_id')
        if not track_id:
            return jsonify({"success": False, "error": "Не указан ID трека"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Недействительный токен"}), 200
        
        response = requests.delete(
            f"{SPOTIFY_API_BASE_URL}/me/tracks",
            headers=headers,
            params={"ids": track_id}
        )
        
        if response.status_code in [200, 204]:
            return jsonify({"success": True})
        
        return jsonify({
            "success": False,
            "error": f"Ошибка API Spotify: {response.status_code}"
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/user-playlists")
def user_playlists():
    """
    Получает список плейлистов пользователя.
    
    Returns:
        JSON со списком плейлистов
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Требуется авторизация"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Недействительный токен"}), 200
        
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
            "error": f"Ошибка API Spotify: {response.status_code}"
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/add-to-playlist", methods=["POST"])
def add_to_playlist():
    """
    Добавляет трек в плейлист.
    
    Returns:
        JSON с результатом операции
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Требуется авторизация"}), 200
        
        data = request.json
        playlist_id = data.get('playlist_id')
        track_uri = data.get('track_uri')
        
        if not playlist_id or not track_uri:
            return jsonify({"success": False, "error": "Не указан ID плейлиста или URI трека"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Недействительный токен"}), 200
        
        response = requests.post(
            f"{SPOTIFY_API_BASE_URL}/playlists/{playlist_id}/tracks",
            headers=headers,
            json={"uris": [track_uri]}
        )
        
        if response.status_code in [201, 200]:
            return jsonify({"success": True})
        
        return jsonify({
            "success": False,
            "error": f"Ошибка API Spotify: {response.status_code}"
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/play-track", methods=["POST"])
def play_track():
    """
    Воспроизводит указанный трек в Spotify.
    
    Returns:
        JSON с результатом операции
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Требуется авторизация"}), 200
        
        data = request.json
        uri = data.get('uri')
        
        if not uri:
            return jsonify({"success": False, "error": "Не указан URI трека"}), 200
        
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Недействительный токен"}), 200
        
        # Формируем запрос с URI трека
        payload = {
            "uris": [uri] if ":" in uri else None,
            "context_uri": uri if ":" not in uri else None
        }
        
        # Удаляем None значения
        payload = {k: v for k, v in payload.items() if v is not None}
        
        # Воспроизводим трек
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
            "error": f"Ошибка API Spotify: {response.status_code}{error_info}"
        }), 200
        
    except Exception as e:
        logger.error(f"Ошибка при воспроизведении трека: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/get-similar-tracks", methods=["GET"])
def get_similar_tracks_endpoint():
    """
    Эндпоинт для получения похожих треков по ID.
    
    Query параметры:
        track_id (str): ID трека Spotify
    
    Returns:
        JSON с похожими треками или сообщением об ошибке
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Требуется авторизация"}), 200
            
        track_id = request.args.get('track_id')
        if not track_id:
            return jsonify({"success": False, "error": "Не указан ID трека"}), 200
            
        # Получаем похожие треки
        result = get_similar_tracks(track_id)
        
        # Возвращаем результат
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Ошибка при получении похожих треков: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/save-tracks-to-session", methods=["POST"])
def save_tracks_to_session():
    """
    Сохраняет список треков в сессии пользователя.
    
    Returns:
        JSON response с подтверждением
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
    Возвращает треки из сессии в формате JSON
    
    Returns:
        JSON с треками из сессии
    """
    try:
        tracks = session.get("recommended_tracks", [])
        return jsonify({"success": True, "tracks": tracks})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@spotify_bp.route("/get-my-playlists")
def get_my_playlists():
    """
    Получает список плейлистов пользователя.
    
    Returns:
        JSON с плейлистами пользователя
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Требуется авторизация"}), 200
        
        # Получаем заголовки с токеном
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Недействительный токен"}), 200
        
        # Получаем плейлисты пользователя
        playlists = []
        next_url = f"{SPOTIFY_API_BASE_URL}/me/playlists?limit=50"
        
        while next_url:
            response = requests.get(next_url, headers=headers)
            
            if response.status_code != 200:
                return jsonify({"success": False, "error": f"Ошибка API Spotify: {response.status_code}"}), 200
                
            data = response.json()
            playlists.extend(data["items"])
            next_url = data.get("next")
        
        logger.info(f"Получено {len(playlists)} плейлистов пользователя")
        return jsonify({"success": True, "playlists": playlists})
            
    except Exception as e:
        logger.error(f"Ошибка при получении плейлистов: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/add-track-to-playlist", methods=["POST"])
def add_track_to_playlist():
    """
    Добавляет трек в указанный плейлист.
    
    Returns:
        JSON с результатом операции
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Требуется авторизация"}), 200
        
        # Получаем данные из запроса
        data = request.json
        if not data or "playlist_id" not in data or "track_uri" not in data:
            return jsonify({"success": False, "error": "Не указан ID плейлиста или URI трека"}), 200
        
        playlist_id = data["playlist_id"]
        track_uri = data["track_uri"]
        
        # Получаем заголовки с токеном
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Недействительный токен"}), 200
        
        # Добавляем трек в плейлист
        response = requests.post(
            f"{SPOTIFY_API_BASE_URL}/playlists/{playlist_id}/tracks",
            headers=headers,
            json={"uris": [track_uri]}
        )
        
        if response.status_code in [200, 201]:
            logger.info(f"Трек {track_uri} успешно добавлен в плейлист {playlist_id}")
            return jsonify({"success": True})
        else:
            error_message = "Ошибка при добавлении трека в плейлист"
            try:
                error_data = response.json()
                if "error" in error_data and "message" in error_data["error"]:
                    error_message = error_data["error"]["message"]
            except:
                pass
            
            logger.error(f"Ошибка при добавлении трека в плейлист: {response.status_code} {error_message}")
            return jsonify({"success": False, "error": error_message}), 200
            
    except Exception as e:
        logger.error(f"Ошибка при добавлении трека в плейлист: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/add-all-tracks-to-playlist", methods=["POST"])
def add_all_tracks_to_playlist():
    """
    Добавляет все треки из сессии в указанный плейлист.
    
    Returns:
        JSON с результатом операции
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Требуется авторизация"}), 200
        
        # Получаем данные из запроса
        data = request.json
        if not data or "playlist_id" not in data:
            return jsonify({"success": False, "error": "Не указан ID плейлиста"}), 200
        
        playlist_id = data["playlist_id"]
        
        # Получаем треки из сессии
        tracks = session.get("recommended_tracks", [])
        
        if not tracks:
            return jsonify({"success": False, "error": "Нет треков для добавления"}), 200
        
        # Получаем заголовки с токеном
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Недействительный токен"}), 200
        
        # Преобразуем треки в URI формат
        track_uris = []
        for track in tracks:
            track_id = None
            
            if isinstance(track, str):
                # Если это просто строка ID
                track_id = track
            elif isinstance(track, dict):
                # Если это объект с полями
                track_id = track.get('id')
                if not track_id and 'uri' in track:
                    # Извлекаем ID из URI если есть
                    uri_parts = track['uri'].split(':')
                    if len(uri_parts) == 3 and uri_parts[1] == 'track':
                        track_id = uri_parts[2]
            
            if track_id:
                track_uris.append(f"spotify:track:{track_id}")
        
        if not track_uris:
            return jsonify({"success": False, "error": "Не удалось извлечь ID треков"}), 200
        
        # Добавляем треки в плейлист группами по 100 (ограничение API Spotify)
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
                error_message = "Ошибка при добавлении треков в плейлист"
                try:
                    error_data = response.json()
                    if "error" in error_data and "message" in error_data["error"]:
                        error_message = error_data["error"]["message"]
                except:
                    pass
                
                logger.error(f"Ошибка при добавлении треков в плейлист: {response.status_code} {error_message}")
                return jsonify({"success": False, "error": error_message}), 200
        
        logger.info(f"Добавлено {added_count} треков в плейлист {playlist_id}")
        return jsonify({"success": True, "added_count": added_count})
            
    except Exception as e:
        logger.error(f"Ошибка при добавлении треков в плейлист: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 200

@spotify_bp.route("/create-playlist-with-all-tracks", methods=["POST"])
def create_playlist_with_all_tracks():
    """
    Создает новый плейлист и добавляет в него все треки из сессии.
    
    Returns:
        JSON с результатом операции
    """
    try:
        if "spotify_token" not in session:
            return jsonify({"success": False, "error": "Требуется авторизация"}), 200
        
        # Получаем данные из запроса
        data = request.json
        if not data or "name" not in data:
            return jsonify({"success": False, "error": "Не указано название плейлиста"}), 200
        
        name = data["name"]
        description = data.get("description", "")
        is_public = data.get("public", False)
        
        # Получаем треки из сессии
        tracks = session.get("recommended_tracks", [])
        
        if not tracks:
            return jsonify({"success": False, "error": "Нет треков для добавления"}), 200
        
        # Получаем заголовки с токеном
        headers = get_headers()
        if not headers:
            return jsonify({"success": False, "error": "Недействительный токен"}), 200
        
        # Получаем ID пользователя
        user_response = requests.get(f"{SPOTIFY_API_BASE_URL}/me", headers=headers)
        if user_response.status_code != 200:
            return jsonify({"success": False, "error": "Не удалось получить данные пользователя"}), 200
        
        user_id = user_response.json()["id"]
        
        # Создаем плейлист
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
            error_message = "Ошибка при создании плейлиста"
            try:
                error_data = playlist_response.json()
                if "error" in error_data and "message" in error_data["error"]:
                    error_message = error_data["error"]["message"]
            except:
                pass
            
            logger.error(f"Ошибка при создании плейлиста: {playlist_response.status_code} {error_message}")
            return jsonify({"success": False, "error": error_message}), 200
        
        playlist_data = playlist_response.json()
        playlist_id = playlist_data["id"]
        
        logger.info(f"Создан плейлист {name} (ID: {playlist_id})")
        
        # Преобразуем треки в URI формат
        track_uris = []
        for track in tracks:
            track_id = None
            
            if isinstance(track, str):
                # Если это просто строка ID
                track_id = track
            elif isinstance(track, dict):
                # Если это объект с полями
                track_id = track.get('id')
                if not track_id and 'uri' in track:
                    # Извлекаем ID из URI если есть
                    uri_parts = track['uri'].split(':')
                    if len(uri_parts) == 3 and uri_parts[1] == 'track':
                        track_id = uri_parts[2]
            
            if track_id:
                track_uris.append(f"spotify:track:{track_id}")
        
        # Добавляем треки в плейлист группами по 100 (ограничение API Spotify)
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
                logger.warning(f"Ошибка при добавлении треков в новый плейлист: {response.status_code}")
        
        logger.info(f"Добавлено {added_count} треков в новый плейлист {playlist_id}")
        
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
        logger.error(f"Ошибка при создании плейлиста: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 200