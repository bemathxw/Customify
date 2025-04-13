# Customify

## Project Description

This web application allows users to get personalized music recommendations based on their favorite tracks on Spotify, add them to a playlist, and to the playback queue. The app uses the Spotify API to authenticate users and get data about their musical preferences.

## Main Features

- Authorization via Spotify OAuth
- Display of user's top tracks
- Generation of personalized recommendations
- Ability to add recommended tracks to a playlist
- For Spotify Premium users: adding tracks to the playback queue

## Installation and Setup

1. Clone the repository:
   ```
   git clone https://github.com/your-username/spotify-recommendations.git
   cd spotify-recommendations
   ```

2. Create a virtual environment and install dependencies:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Create a `.env` file with the following variables:
   ```
   FLASK_SECRET_KEY=your_secret_key
   SPOTIFY_CLIENT_ID=your_spotify_client_id
   SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
   ```

4. Run the application:
   ```
   python app.py
   ```

5. Open your browser and go to `http://127.0.0.1:5000`

## Getting Spotify API Keys

To make the app work, you need to create an application in the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/) and get a Client ID and Client Secret.

## Code Documentation Guidelines

When contributing to this project, please follow these documentation guidelines:

1. All functions should be documented using PEP 257 docstring conventions.
2. Use triple double quotes (`"""`) for docstrings.
3. Include a brief description of what the function does.
4. Document all parameters using the `Args:` section.
5. Document return values using the `Returns:` section.
6. Document exceptions raised using the `Raises:` section (if applicable).

Example:
```python
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
        
    Raises:
        ConnectionError: If unable to connect to Spotify API
    """
    # Function implementation
```

---

# Customify

## Опис проекту

Цей веб-додаток дозволяє користувачам отримувати персоналізовані музичні рекомендації на основі їхніх улюблених треків у Spotify, додавати їх до плейлисту та до черги відтворення. Додаток використовує Spotify API для аутентифікації користувачів та отримання даних про їхні музичні вподобання.

## Основні функції

- Авторизація через Spotify OAuth
- Відображення топ-треків користувача
- Генерація персоналізованих рекомендацій
- Можливість додавати рекомендовані треки до плейлиста
- Для користувачів Spotify Premium: додавання треків до черги відтворення

## Встановлення та запуск

1. Клонуйте репозиторій:
   ```
   git clone https://github.com/your-username/spotify-recommendations.git
   cd spotify-recommendations
   ```

2. Створіть віртуальне середовище та встановіть залежності:
   ```
   python -m venv venv
   source venv/bin/activate  # На Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Створіть файл `.env` з наступними змінними:
   ```
   FLASK_SECRET_KEY=your_secret_key
   SPOTIFY_CLIENT_ID=your_spotify_client_id
   SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
   ```

4. Запустіть додаток:
   ```
   python app.py
   ```

5. Відкрийте браузер і перейдіть за адресою `http://127.0.0.1:5000`

## Отримання Spotify API ключів

Для роботи додатку вам потрібно створити додаток у [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/) та отримати Client ID і Client Secret.

## Рекомендації щодо документування коду

При внесенні змін до цього проекту, будь ласка, дотримуйтесь наступних рекомендацій з документування:

1. Всі функції повинні бути документовані згідно з конвенціями PEP 257.
2. Використовуйте потрійні подвійні лапки (`"""`) для документаційних рядків.
3. Включайте короткий опис того, що робить функція.
4. Документуйте всі параметри, використовуючи розділ `Args:`.
5. Документуйте значення, що повертаються, використовуючи розділ `Returns:`.
6. Документуйте винятки, що виникають, використовуючи розділ `Raises:` (якщо застосовно).

Приклад:
```python
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
        
    Raises:
        ConnectionError: If unable to connect to Spotify API
    """
    # Реалізація функції
```
