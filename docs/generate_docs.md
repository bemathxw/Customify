# Generating Documentation for Customify

This document provides basic instructions on how to generate documentation for the Customify project.

## Prerequisites

Before generating documentation, install pdoc:

```bash
pip install pdoc
```

## Generating HTML Documentation

To generate HTML documentation:

1. Navigate to the project root directory.

2. Run the following command:

   ```bash
   pdoc -o docs spotify.py app.py
   ```

   This will create HTML documentation in the `docs` directory.

3. To view the documentation, open `docs/index.html` in your web browser.

## Running a Documentation Server

For real-time documentation updates:

1. Start the documentation server:

   ```bash
   pdoc -h localhost -p 8080 spotify.py app.py
   ```

2. Open your browser and navigate to http://localhost:8080

## Generating Markdown Documentation

For Markdown format documentation:

```bash
pdoc -o docs-md --format markdown spotify.py app.py
```

## Documentation Style Guide

When writing docstrings, follow these guidelines:

1. Use PEP 257 style docstrings with triple double quotes (`"""`).
2. Include a brief description of what the function/class does.
3. Document parameters using the `Args:` section.
4. Document return values using the `Returns:` section.
5. Document exceptions using the `Raises:` section (if applicable).

Example:

```python
def get_recommendations(track_ids):
    """
    Get recommendations from random tracks of all artists in top-10.
    
    Args:
        track_ids (list): List of Spotify track IDs to use as seed
        
    Returns:
        list: List of recommended track objects or empty list if request fails
    """
    # Function implementation
```

## Troubleshooting

If you encounter issues with pdoc:

1. **Missing module errors**: Make sure all dependencies are installed.
2. **Version conflicts**: Ensure you're using the correct syntax for your version of pdoc.

---

# Генерація документації для Customify

Цей документ містить базові інструкції щодо генерації документації для проекту Customify.

## Передумови

Перед генерацією документації встановіть pdoc:

```bash
pip install pdoc
```

## Генерація HTML-документації

Для генерації HTML-документації:

1. Перейдіть до кореневої директорії проекту.

2. Виконайте наступну команду:

   ```bash
   pdoc -o docs spotify.py app.py
   ```

   Це створить HTML-документацію в директорії `docs`.

3. Для перегляду документації відкрийте `docs/index.html` у вашому веб-браузері.

## Запуск сервера документації

Для оновлення документації в реальному часі:

1. Запустіть сервер документації:

   ```bash
   pdoc -h localhost -p 8080 spotify.py app.py
   ```

2. Відкрийте ваш браузер і перейдіть за адресою http://localhost:8080

## Генерація документації у форматі Markdown

Для документації у форматі Markdown:

```bash
pdoc -o docs-md --format markdown spotify.py app.py
```

## Рекомендації щодо стилю документації

При написанні документаційних рядків дотримуйтесь наступних рекомендацій:

1. Використовуйте документаційні рядки в стилі PEP 257 з потрійними подвійними лапками (`"""`).
2. Включайте короткий опис того, що робить функція/клас.
3. Документуйте параметри, використовуючи розділ `Args:`.
4. Документуйте значення, що повертаються, використовуючи розділ `Returns:`.
5. Документуйте винятки, використовуючи розділ `Raises:` (якщо застосовно).

Приклад:

```python
def get_recommendations(track_ids):
    """
    Get recommendations from random tracks of all artists in top-10.
    
    Args:
        track_ids (list): List of Spotify track IDs to use as seed
        
    Returns:
        list: List of recommended track objects or empty list if request fails
    """
    # Реалізація функції
```

## Усунення проблем

Якщо ви зіткнулися з проблемами при використанні pdoc:

1. **Помилки відсутніх модулів**: Переконайтеся, що всі залежності встановлено.
2. **Конфлікти версій**: Переконайтеся, що ви використовуєте правильний синтаксис для вашої версії pdoc. 