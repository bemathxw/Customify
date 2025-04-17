import time
import functools
from flask import current_app
from loguru import logger

# Простий словник для зберігання кешованих даних
_cache = {}

def cache_data(ttl=300):
    """
    Декоратор для кешування результатів функцій.
    
    Args:
        ttl (int): Час життя кешу в секундах (за замовчуванням 5 хвилин)
    
    Returns:
        Декорована функція з кешуванням результатів
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Створюємо ключ кешу на основі імені функції та аргументів
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Перевіряємо, чи є дані в кеші і чи не застаріли вони
            if cache_key in _cache:
                entry = _cache[cache_key]
                if time.time() < entry['expires']:
                    logger.debug(f"Використовуємо кешовані дані для {func.__name__}")
                    return entry['data']
            
            # Якщо даних немає в кеші або вони застаріли, викликаємо функцію
            result = func(*args, **kwargs)
            
            # Зберігаємо результат у кеші
            _cache[cache_key] = {
                'data': result,
                'expires': time.time() + ttl
            }
            
            logger.debug(f"Кешовано результат для {func.__name__}, TTL: {ttl}с")
            return result
        return wrapper
    return decorator

def clear_cache():
    """Очищає весь кеш."""
    global _cache
    _cache = {}
    logger.info("Кеш очищено")

def clear_cache_for_function(func_name):
    """
    Очищає кеш для конкретної функції.
    
    Args:
        func_name (str): Ім'я функції, кеш якої потрібно очистити
    """
    global _cache
    keys_to_delete = [k for k in _cache if k.startswith(f"{func_name}:")]
    for key in keys_to_delete:
        del _cache[key]
    logger.info(f"Кеш для функції {func_name} очищено")

def get_cache_stats():
    """
    Повертає статистику використання кешу.
    
    Returns:
        dict: Статистика кешу
    """
    return {
        'total_entries': len(_cache),
        'entries_by_function': {
            func_name: len([k for k in _cache if k.startswith(f"{func_name}:")])
            for func_name in set(k.split(':')[0] for k in _cache)
        }
    } 