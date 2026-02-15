"""
Управление глобальным стопом системы (Redis primary, SQLite fallback).
Глобальный стоп останавливает ALL фоновые процессы в ОБОИХ окружениях (prod и sandbox).

⚠️ КРИТИЧНОЕ: Для синхронизации между prod и sandbox служба ТРЕБУЕТ:
   1. REDIS_URL как Shared Variable в Railway (одна на обе services)
   2. Оба сервиса должны быть подключены к одному Redis инстансу
   
Если REDIS_URL не установлен, используется SQLite fallback, но это изолирует prod и sandbox!
"""
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)
redis_client = None  # Ленивое подключение
_redis_url_warned = False

# asyncio.Event для мгновенной отмены задач (без ожидания sleep)
_global_stop_event: Optional[asyncio.Event] = None
_redis_connected: bool = False
COLLECTION_STOP_KEY = "jur:stop:global"


def _get_redis_client():
    """Ленивое подключение к Redis (имитация singleton)."""
    global redis_client, _redis_connected
    if redis_client is not None:
        return redis_client
    
    try:
        import redis
        from config.config import REDIS_URL
        
        if not REDIS_URL:
            global _redis_url_warned
            if not _redis_url_warned:
                logger.warning("⚠️  REDIS_URL not set! Global stop will NOT synchronize between prod and sandbox.")
                logger.warning("   → Set REDIS_URL as Shared Variable in Railway for prod-bot AND sandbox-bot services")
                _redis_url_warned = True
            _redis_connected = False
            return None
        
        redis_client = redis.Redis.from_url(REDIS_URL, socket_timeout=2, socket_connect_timeout=2)
        redis_client.ping()
        _redis_connected = True
        logger.info("✓ Redis connected for global_stop synchronization")
        return redis_client
    except Exception as e:
        logger.warning(f"⚠️  Redis unavailable: {e} → Using SQLite fallback (NOT synchronized between services!)")
        _redis_connected = False
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
                if isinstance(value, bytes):
                    value = value.decode()
                return str(value) == "1"

            value = redis.get(COLLECTION_STOP_KEY)
            if value is not None:
                if isinstance(value, bytes):
                    value = value.decode()
                return str(value) == "1"
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
    ПОБОЧНЫЙ ЭФФЕКТ: устанавливает asyncio.Event для мгновенной отмены задач.
    """
    str_value = "1" if value else "0"
    
    # Пытаемся Redis
    redis = _get_redis_client()
    if redis:
        try:
            if value:
                redis.set("system:global_stop", "1")
                redis.set(COLLECTION_STOP_KEY, "1")
            else:
                redis.delete("system:global_stop")
                redis.delete(COLLECTION_STOP_KEY)
            logger.info(f"Global stop set to {str_value} (Redis)")
            _notify_global_stop_changed(value)
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
            logger.info(f"Global stop set to {str_value} (SQLite fallback - NO sync!)")
            _notify_global_stop_changed(value)
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
        backend = "SQLite (fallback - NO SYNC!)"
    
    status = "🔴 ОСТАНОВЛЕНА" if stopped else "🟢 РАБОТАЕТ"
    status_str = f"{status} ({backend})"
    
    return stopped, status_str


# === asyncio.Event интеграция для мгновенной отмены задач ===

async def init_global_stop_event():
    """Инициализировать asyncio.Event (вызвать при старте бота)."""
    global _global_stop_event
    _global_stop_event = asyncio.Event()
    # Если глобальный стоп уже активен, сразу установить событие
    if get_global_stop():
        _global_stop_event.set()
    logger.info("Global stop asyncio.Event initialized")


def _notify_global_stop_changed(value: bool):
    """Уведомить asyncio.Event об изменении стопа."""
    global _global_stop_event
    if _global_stop_event is None:
        return
    
    try:
        if value:
            _global_stop_event.set()
            logger.info("asyncio.Event SET - задачи получат сигнал отмены")
        else:
            _global_stop_event.clear()
            logger.info("asyncio.Event CLEARED - сбор возобновлен")
    except Exception as e:
        logger.error(f"Error notifying global_stop_event: {e}")


async def wait_global_stop():
    """
    Ждать сигнала глобального стопа (используется в задачах сбора).
    EXAMPLE:
        try:
            await wait_global_stop()  # Ждет активации стопа
            logger.info("Global stop activated - cancelling collection")
        except asyncio.CancelledError:
            pass
    """
    global _global_stop_event
    if _global_stop_event is None:
        # Событие не инициализировано, ждем в цикле
        while True:
            if get_global_stop():
                return
            await asyncio.sleep(1)
    else:
        # Используем событие (мгновенно!)
        await _global_stop_event.wait()


async def wait_for_resume():
    """
    Ждать возобновления после стопа (используется при пауз в collect loop).
    EXAMPLE:
        if get_global_stop():
            logger.info("Waiting for resume signal...")
            await wait_for_resume()
            logger.info("Resumed!")
    """
    global _global_stop_event
    while get_global_stop():
        await asyncio.sleep(1)
    if _global_stop_event is not None:
        _global_stop_event.clear()
