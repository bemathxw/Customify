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
