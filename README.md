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

## Developer Setup Guide

This guide will help you set up the Customify project on a fresh system.

### Prerequisites

1. **Install Python**:
   - **Windows**: Download and install from [python.org](https://www.python.org/downloads/) (version 3.8 or higher)
   - **macOS**: `brew install python`
   - **Linux**: `sudo apt install python3 python3-pip`

2. **Install Git**:
   - **Windows**: Download and install from [git-scm.com](https://git-scm.com/download/win)
   - **macOS**: `brew install git`
   - **Linux**: `sudo apt install git`

### Project Setup

1. **Clone the repository**:
   ```
   git clone https://github.com/your-username/customify.git
   cd customify
   ```

2. **Create a virtual environment**:
   ```
   python -m venv venv
   ```

3. **Activate the virtual environment**:
   - **Windows**: `venv\Scripts\activate`
   - **macOS/Linux**: `source venv/bin/activate`

4. **Install dependencies**:
   ```
   pip install -r requirements.txt
   ```
   This will install all required packages listed in the requirements.txt file.

### Configuration

1. **Create a Spotify Developer account**:
   - Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/)
   - Create a new application
   - Set the redirect URI to `http://127.0.0.1:5000/spotify/callback`
   - Note your Client ID and Client Secret

2. **Create environment variables file**:
   Create a `.env` file in the project root with the following content:
   ```
   FLASK_SECRET_KEY=your_random_secret_key
   SPOTIFY_CLIENT_ID=your_spotify_client_id
   SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
   ```

### Running the Application

1. **Start the development server**:
   ```
   python app.py
   ```

2. **Access the application**:
   Open your browser and go to `http://127.0.0.1:5000`

### Basic Commands

- **Run the application**: `python app.py`
- **Generate documentation**: `pdoc -o docs spotify.py app.py`
- **View documentation**: Open `docs/index.html` in your browser
- **Run documentation server**: `pdoc -h localhost -p 8080 spotify.py app.py`

### Development Workflow

1. Create a new branch for your feature: `git checkout -b feature-name`
2. Make your changes
3. Test your changes locally
4. Commit your changes: `git commit -m "Description of changes"`
5. Push your branch: `git push origin feature-name`
6. Create a pull request on GitHub

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

## Інструкція для розробників

Цей посібник допоможе вам налаштувати проект Customify на новій системі.

### Передумови

1. **Встановлення Python**:
   - **Windows**: Завантажте та встановіть з [python.org](https://www.python.org/downloads/) (версія 3.8 або вище)
   - **macOS**: `brew install python`
   - **Linux**: `sudo apt install python3 python3-pip`

2. **Встановлення Git**:
   - **Windows**: Завантажте та встановіть з [git-scm.com](https://git-scm.com/download/win)
   - **macOS**: `brew install git`
   - **Linux**: `sudo apt install git`

### Налаштування проекту

1. **Клонування репозиторію**:
   ```
   git clone https://github.com/your-username/customify.git
   cd customify
   ```

2. **Створення віртуального середовища**:
   ```
   python -m venv venv
   ```

3. **Активація віртуального середовища**:
   - **Windows**: `venv\Scripts\activate`
   - **macOS/Linux**: `source venv/bin/activate`

4. **Встановлення залежностей**:
   ```
   pip install -r requirements.txt
   ```
   This will install all required packages listed in the requirements.txt file.

### Конфігурація

1. **Створення облікового запису Spotify Developer**:
   - Перейдіть на [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/)
   - Створіть новий додаток
   - Встановіть URI перенаправлення на `http://127.0.0.1:5000/spotify/callback`
   - Запишіть ваш Client ID та Client Secret

2. **Створення файлу змінних середовища**:
   Створіть файл `.env` в кореневій папці проекту з наступним вмістом:
   ```
   FLASK_SECRET_KEY=your_random_secret_key
   SPOTIFY_CLIENT_ID=your_spotify_client_id
   SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
   ```

### Запуск додатку

1. **Запуск сервера розробки**:
   ```
   python app.py
   ```

2. **Доступ до додатку**:
   Відкрийте браузер і перейдіть за адресою `http://127.0.0.1:5000`

### Основні команди

- **Запуск додатку**: `python app.py`
- **Генерація документації**: `pdoc -o docs spotify.py app.py`
- **Перегляд документації**: Відкрийте `docs/index.html` у вашому браузері
- **Запуск сервера документації**: `pdoc -h localhost -p 8080 spotify.py app.py`

### Робочий процес розробки

1. Створіть нову гілку для вашої функції: `git checkout -b назва-функції`
2. Внесіть зміни
3. Протестуйте зміни локально
4. Зробіть коміт змін: `git commit -m "Опис змін"`
5. Відправте вашу гілку: `git push origin назва-функції`
6. Створіть pull request на GitHub