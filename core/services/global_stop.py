"""
Управление глобальным стопом системы (Redis primary, SQLite fallback).
Глобальный стоп останавливает ALL фоновые процессы в ОБОИХ окружениях (prod и sandbox).
"""
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)
redis_client = None  # Ленивое подключение


def _get_redis_client():
    """Ленивое подключение к Redis (имитация singleton)."""
    global redis_client
    if redis_client is not None:
        return redis_client
    
    try:
        import redis
        from config.config import REDIS_URL
        
        if not REDIS_URL:
            logger.debug("REDIS_URL not set, global_stop will use SQLite fallback")
            return None
        
        redis_client = redis.Redis.from_url(REDIS_URL, socket_timeout=2, socket_connect_timeout=2)
        redis_client.ping()
        logger.info("Redis connected for global_stop")
        return redis_client
    except Exception as e:
        logger.debug(f"Redis unavailable for global_stop: {e}")
        return None


def _get_db_fallback():
    """Fallback на SQLite из текущего окружения."""
    try:
        from config.config import DATABASE_PATH
        import sqlite3
        import os
        
        if not os.path.exists(DATABASE_PATH):
            return None
        
        conn = sqlite3.connect(DATABASE_PATH, timeout=5)
        
        # Создаем таблицу если её нет
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        
        return conn
    except Exception as e:
        logger.debug(f"SQLite fallback unavailable: {e}")
        return None


def get_global_stop() -> bool:
    """
    Получить статус глобального стопа.
    Возвращает True если система остановлена.
    """
    # Пытаемся Redis
    redis = _get_redis_client()
    if redis:
        try:
            value = redis.get("system:global_stop")
            if value is not None:
                return value.decode() == "1"
        except Exception as e:
            logger.debug(f"Redis read error (global_stop): {e}")
    
    # Fallback на SQLite
    try:
        db = _get_db_fallback()
        if db:
            cursor = db.cursor()
            cursor.execute("SELECT value FROM system_settings WHERE key = 'global_stop'")
            row = cursor.fetchone()
            db.close()
            if row:
                return row[0] == "1"
    except Exception as e:
        logger.debug(f"SQLite read error (global_stop): {e}")
    
    # По умолчанию стоп отключен
    return False


def set_global_stop(value: bool) -> bool:
    """
    Установить статус глобального стопа.
    Возвращает True если успешно установлено.
    """
    str_value = "1" if value else "0"
    
    # Пытаемся Redis
    redis = _get_redis_client()
    if redis:
        try:
            redis.set("system:global_stop", str_value)
            logger.info(f"Global stop set to {str_value} (Redis)")
            return True
        except Exception as e:
            logger.warning(f"Redis write error (global_stop): {e}")
    
    # Fallback на SQLite
    try:
        db = _get_db_fallback()
        if db:
            cursor = db.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
                ("global_stop", str_value)
            )
            db.commit()
            db.close()
            logger.info(f"Global stop set to {str_value} (SQLite fallback)")
            return True
    except Exception as e:
        logger.error(f"SQLite write error (global_stop): {e}")
    
    logger.error("Failed to set global_stop: neither Redis nor SQLite available")
    return False


def toggle_global_stop() -> bool:
    """
    Переключить глобальный стоп.
    Возвращает новое значение.
    """
    current = get_global_stop()
    new_value = not current
    set_global_stop(new_value)
    logger.info(f"Global stop toggled from {current} to {new_value}")
    return new_value


def is_redis_available() -> bool:
    """Проверить, доступен ли Redis."""
    return _get_redis_client() is not None


def get_global_stop_status_str() -> tuple[bool, str]:
    """
    Получить статус стопа с информацией о backend'е.
    Возвращает (is_stopped, status_string).
    """
    stopped = get_global_stop()
    redis_ok = is_redis_available()
    
    if redis_ok:
        backend = "Redis"
    else:
        backend = "SQLite (fallback)"
    
    status = "🔴 ОСТАНОВЛЕНА" if stopped else "🟢 РАБОТАЕТ"
    status_str = f"{status} ({backend})"
    
    return stopped, status_str
