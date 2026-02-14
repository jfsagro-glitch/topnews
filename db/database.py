"""
Управление базой данных для хранения опубликованных новостей
"""
import sqlite3
import time
import re
from datetime import datetime, timezone
from typing import List, Tuple, Optional
import logging
import os
import threading

logger = logging.getLogger(__name__)


class NewsDatabase:
    """Управление БД опубликованных новостей"""
    
    def __init__(self, db_path: str = 'db/news.db'):
        self.db_path = db_path
        logger.info(f"Initializing NewsDatabase with path: {db_path}")
        os.makedirs(os.path.dirname(self.db_path) or '.', exist_ok=True)

        # Single shared connection + a lock to serialize write operations
        self._conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        self._write_lock = threading.Lock()

        # Initialize DB (PRAGMAs + table)
        try:
            cursor = self._conn.cursor()
            try:
                cursor.execute("PRAGMA journal_mode=WAL;")
            except Exception:
                pass
            try:
                cursor.execute("PRAGMA busy_timeout=10000;")
            except Exception:
                pass
            try:
                cursor.execute("PRAGMA cache_size = -20000;")  # Ограничение кэша ~20MB для оптимизации Railway
            except Exception:
                pass
            try:
                cursor.execute("PRAGMA temp_store = MEMORY;")
            except Exception:
                pass

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS published_news (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL,
                    category TEXT NOT NULL,
                    lead_text TEXT,
                    raw_text TEXT,
                    clean_text TEXT,
                    checksum TEXT,
                    content_hash TEXT,
                    language TEXT,
                    domain TEXT,
                    extraction_method TEXT,
                    published_date TEXT,
                    published_time TEXT,
                    published_confidence TEXT,
                    published_source TEXT,
                    fetched_at TIMESTAMP,
                    first_seen_at TIMESTAMP,
                    url_hash TEXT,
                    url_normalized TEXT,
                    guid TEXT,
                    simhash INTEGER,
                    quality_score REAL,
                    hashtags_ru TEXT,
                    hashtags_en TEXT,
                    telegram_message_id INTEGER,
                    ai_summary TEXT,
                    ai_summary_created_at TIMESTAMP,
                    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Create index on title for faster duplicate checks
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_title ON published_news(title)
            ''')

            # Table for storing RSS ETag and Last-Modified headers
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS rss_state (
                    url TEXT PRIMARY KEY,
                    etag TEXT,
                    last_modified TEXT
                )
            ''')

            # Table for caching RSS items (for 304 Not Modified responses)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS rss_cache (
                    url TEXT PRIMARY KEY,
                    items TEXT NOT NULL,
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Table for bot instance lock (to prevent double запуск)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bot_lock (
                    name TEXT PRIMARY KEY,
                    instance_id TEXT NOT NULL,
                    locked_at TIMESTAMP NOT NULL
                )
            ''')

            # Table for caching AI summaries (legacy)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ai_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    news_id INTEGER NOT NULL UNIQUE,
                    summary_text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (news_id) REFERENCES published_news(id) ON DELETE CASCADE
                )
            ''')

            # Table for LLM response cache (hash-based)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS llm_cache (
                    cache_key TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_llm_cache_expires ON llm_cache(expires_at)
            ''')

            # Table for AI usage totals (persistent across deploys)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ai_usage (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    total_requests INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    total_cost_usd REAL NOT NULL DEFAULT 0.0,
                    summarize_requests INTEGER NOT NULL DEFAULT 0,
                    summarize_tokens INTEGER NOT NULL DEFAULT 0,
                    category_requests INTEGER NOT NULL DEFAULT 0,
                    category_tokens INTEGER NOT NULL DEFAULT 0,
                    text_clean_requests INTEGER NOT NULL DEFAULT 0,
                    text_clean_tokens INTEGER NOT NULL DEFAULT 0,
                    daily_cost_usd REAL NOT NULL DEFAULT 0.0,
                    daily_cost_date TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                INSERT OR IGNORE INTO ai_usage (id, total_requests, total_tokens, total_cost_usd)
                VALUES (1, 0, 0, 0.0)
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ai_usage_daily (
                    date TEXT PRIMARY KEY,
                    tokens_in INTEGER NOT NULL DEFAULT 0,
                    tokens_out INTEGER NOT NULL DEFAULT 0,
                    cost_usd REAL NOT NULL DEFAULT 0.0,
                    calls INTEGER NOT NULL DEFAULT 0,
                    cache_hits INTEGER NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Table for news sources
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    enabled_global INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Table for per-user source settings
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_source_settings (
                    user_id TEXT NOT NULL,
                    source_id INTEGER NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    env TEXT DEFAULT 'prod',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, source_id),
                    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
                )
            ''')

            # Tables for source health status
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS source_health (
                    source TEXT PRIMARY KEY,
                    last_success_at TIMESTAMP,
                    last_error_at TIMESTAMP,
                    last_error_code TEXT,
                    last_error_message TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS source_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    error_code TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Table for per-source quality metrics (for auto-tuning)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS source_quality (
                    source TEXT PRIMARY KEY,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    items_total INTEGER NOT NULL DEFAULT 0,
                    items_new INTEGER NOT NULL DEFAULT 0,
                    items_duplicate INTEGER NOT NULL DEFAULT 0,
                    quality_score REAL NOT NULL DEFAULT 0.0,
                    last_error_code TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Table for per-source fetch scheduling (RSS/RSSHub throttling)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS source_fetch_state (
                    url TEXT PRIMARY KEY,
                    source_name TEXT,
                    next_fetch_at REAL,
                    last_fetch_at REAL,
                    last_status TEXT,
                    error_streak INTEGER DEFAULT 0,
                    last_error_code TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # System settings (shared: global stop, RSSHub toggles)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_source_events_source_time
                ON source_events(source, created_at)
            ''')

            # Table for feature flags (admin settings like AI levels)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS feature_flags (
                    user_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, key)
                )
            ''')

            # Table for user news selections (persistent across restarts)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_news_selections (
                    user_id TEXT NOT NULL,
                    news_id INTEGER NOT NULL,
                    env TEXT DEFAULT 'prod',
                    selected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, news_id),
                    FOREIGN KEY (news_id) REFERENCES published_news(id) ON DELETE CASCADE
                )
            ''')

            # Table for invite codes (access control)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS invites (
                    code TEXT PRIMARY KEY,
                    created_by TEXT NOT NULL,
                    invite_label TEXT,
                    used_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    used_at TIMESTAMP
                )
            ''')

            # Table for approved users (who have access to prod bot)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS approved_users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    invited_by TEXT,
                    invite_label TEXT,
                    approved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Table for user preferences (pause state, etc)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id TEXT PRIMARY KEY,
                    env TEXT DEFAULT 'prod',
                    is_paused INTEGER DEFAULT 0,
                    paused_at TIMESTAMP NULL,
                    resume_at TIMESTAMP NULL,
                    last_delivered_news_id INTEGER NULL,
                    pause_version INTEGER NOT NULL DEFAULT 0,
                    translate_enabled INTEGER DEFAULT 0,
                    translate_lang TEXT DEFAULT 'ru',
                    category_filter TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Table for delivery log to ensure idempotent per-user delivery
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS delivery_log (
                    user_id TEXT NOT NULL,
                    news_id INTEGER NOT NULL,
                    delivered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, news_id)
                )
            ''')

            # Table for cached translations (by news_id + checksum + target language)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS translation_cache_v2 (
                    news_id INTEGER NOT NULL,
                    checksum TEXT NOT NULL,
                    target_lang TEXT NOT NULL,
                    translated_text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (news_id, checksum, target_lang)
                )
            ''')

            # Table for global system settings
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_settings (
                    setting_key TEXT PRIMARY KEY,
                    setting_value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Table for bot settings (global admin-controlled)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Ensure new columns exist for older DBs
            self._ensure_columns(cursor)
            self._ensure_indexes(cursor)

            self._conn.commit()
        except Exception as e:
            logger.error(f"Error initializing DB: {e}")

        logger.info(f"Database initialized at {self.db_path}")
    
    def _ensure_db_exists(self):
        """Создает таблицу, если её нет"""
        os.makedirs(os.path.dirname(self.db_path) or '.', exist_ok=True)
        # Use a short timeout and enable WAL to reduce "database is locked" errors
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        cursor = conn.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL;")
        except Exception:
            pass
        try:
            cursor.execute("PRAGMA busy_timeout=5000;")
        except Exception:
            pass
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS published_news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                source TEXT NOT NULL,
                category TEXT NOT NULL,
                lead_text TEXT,
                raw_text TEXT,
                clean_text TEXT,
                checksum TEXT,
                content_hash TEXT,
                language TEXT,
                domain TEXT,
                extraction_method TEXT,
                published_date TEXT,
                published_time TEXT,
                published_confidence TEXT,
                published_source TEXT,
                fetched_at TIMESTAMP,
                first_seen_at TIMESTAMP,
                url_hash TEXT,
                url_normalized TEXT,
                guid TEXT,
                simhash INTEGER,
                quality_score REAL,
                hashtags_ru TEXT,
                hashtags_en TEXT,
                telegram_message_id INTEGER,
                ai_summary TEXT,
                ai_summary_created_at TIMESTAMP,
                published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self._ensure_columns(cursor)
        self._ensure_indexes(cursor)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                news_id INTEGER NOT NULL UNIQUE,
                summary_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (news_id) REFERENCES published_news(id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_usage (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                total_requests INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                total_cost_usd REAL NOT NULL DEFAULT 0.0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            INSERT OR IGNORE INTO ai_usage (id, total_requests, total_tokens, total_cost_usd)
            VALUES (1, 0, 0, 0.0)
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_usage_daily (
                date TEXT PRIMARY KEY,
                tokens_in INTEGER NOT NULL DEFAULT 0,
                tokens_out INTEGER NOT NULL DEFAULT 0,
                cost_usd REAL NOT NULL DEFAULT 0.0,
                calls INTEGER NOT NULL DEFAULT 0,
                cache_hits INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {self.db_path}")

    def _ensure_columns(self, cursor):
        """Ensure new columns exist for existing databases."""
        try:
            cursor.execute("PRAGMA table_info(published_news)")
            existing = {row[1] for row in cursor.fetchall()}
            required = {
                'lead_text': 'TEXT',
                'raw_text': 'TEXT',
                'clean_text': 'TEXT',
                'checksum': 'TEXT',
                'content_hash': 'TEXT',
                'language': 'TEXT',
                'domain': 'TEXT',
                'extraction_method': 'TEXT',
                'published_date': 'TEXT',
                'published_time': 'TEXT',
                'published_confidence': 'TEXT',
                'published_source': 'TEXT',
                'fetched_at': 'TIMESTAMP',
                'first_seen_at': 'TIMESTAMP',
                'url_hash': 'TEXT',
                'url_normalized': 'TEXT',
                'guid': 'TEXT',
                'simhash': 'INTEGER',
                'quality_score': 'REAL',
                'hashtags_ru': 'TEXT',
                'hashtags_en': 'TEXT',
                'telegram_message_id': 'INTEGER',
                'ai_summary': 'TEXT',
                'ai_summary_created_at': 'TIMESTAMP'
            }
            for column, col_type in required.items():
                if column not in existing:
                    cursor.execute(f"ALTER TABLE published_news ADD COLUMN {column} {col_type}")
        except Exception as e:
            logger.debug(f"Error ensuring columns: {e}")

        try:
            cursor.execute("PRAGMA table_info(user_preferences)")
            existing = {row[1] for row in cursor.fetchall()}
            required = {
                'paused_at': 'TIMESTAMP',
                'resume_at': 'TIMESTAMP',
                'last_delivered_news_id': 'INTEGER',
                'pause_version': 'INTEGER DEFAULT 0',
                'translate_enabled': 'INTEGER DEFAULT 0',
                'translate_lang': "TEXT DEFAULT 'ru'",
                'env': "TEXT DEFAULT 'prod'",
                'category_filter': 'TEXT',
            }
            for column, col_type in required.items():
                if column not in existing:
                    cursor.execute(f"ALTER TABLE user_preferences ADD COLUMN {column} {col_type}")
        except Exception as e:
            logger.debug(f"Error ensuring user_preferences columns: {e}")

        try:
            cursor.execute("PRAGMA table_info(user_source_settings)")
            existing = {row[1] for row in cursor.fetchall()}
            if 'env' not in existing:
                cursor.execute("ALTER TABLE user_source_settings ADD COLUMN env TEXT DEFAULT 'prod'")
        except Exception as e:
            logger.debug(f"Error ensuring user_source_settings columns: {e}")

        try:
            cursor.execute("PRAGMA table_info(user_news_selections)")
            existing = {row[1] for row in cursor.fetchall()}
            if 'env' not in existing:
                cursor.execute("ALTER TABLE user_news_selections ADD COLUMN env TEXT DEFAULT 'prod'")
        except Exception as e:
            logger.debug(f"Error ensuring user_news_selections columns: {e}")

        try:
            cursor.execute("PRAGMA table_info(invites)")
            existing = {row[1] for row in cursor.fetchall()}
            if 'invite_label' not in existing:
                cursor.execute("ALTER TABLE invites ADD COLUMN invite_label TEXT")
        except Exception as e:
            logger.debug(f"Error ensuring invites columns: {e}")

        try:
            cursor.execute("PRAGMA table_info(approved_users)")
            existing = {row[1] for row in cursor.fetchall()}
            if 'invite_label' not in existing:
                cursor.execute("ALTER TABLE approved_users ADD COLUMN invite_label TEXT")
        except Exception as e:
            logger.debug(f"Error ensuring approved_users columns: {e}")

        try:
            cursor.execute("PRAGMA table_info(sources)")
            existing = {row[1] for row in cursor.fetchall()}
            required = {
                'tier': "TEXT DEFAULT 'B'",
                'min_interval_seconds': 'INTEGER',
                'max_items_per_fetch': 'INTEGER',
            }
            for column, col_type in required.items():
                if column not in existing:
                    cursor.execute(f"ALTER TABLE sources ADD COLUMN {column} {col_type}")
        except Exception as e:
            logger.debug(f"Error ensuring sources columns: {e}")

    def _ensure_indexes(self, cursor):
        """Ensure indexes exist after columns are added."""
        try:
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_url_hash ON published_news(url_hash)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_url_normalized ON published_news(url_normalized)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_simhash ON published_news(simhash)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_guid ON published_news(guid)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_checksum ON published_news(checksum)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_content_hash ON published_news(content_hash)
            ''')
        except Exception as e:
            logger.debug(f"Error ensuring indexes: {e}")
    
    def add_news(
        self,
        url: str,
        title: str,
        source: str,
        category: str,
        lead_text: str = "",
        raw_text: str | None = None,
        clean_text: str | None = None,
        checksum: str | None = None,
        content_hash: str | None = None,
        language: str | None = None,
        domain: str | None = None,
        extraction_method: str | None = None,
        published_at: str | None = None,
        published_date: str | None = None,
        published_time: str | None = None,
        published_confidence: str | None = None,
        published_source: str | None = None,
        fetched_at: str | None = None,
        first_seen_at: str | None = None,
        url_hash: str | None = None,
        url_normalized: str | None = None,
        guid: str | None = None,
        simhash: int | None = None,
        quality_score: float | None = None,
        hashtags_ru: str | None = None,
        hashtags_en: str | None = None,
    ) -> int | None:
        """
        Добавляет новость в БД.
        Возвращает news_id если добавлена, иначе None.
        """
        if published_at is None:
            published_at = datetime.now(timezone.utc).isoformat()
        # Retry loop to handle transient "database is locked" errors
        attempts = 3
        for attempt in range(1, attempts + 1):
            try:
                with self._write_lock:
                    cursor = self._conn.cursor()
                    cursor.execute('''
                        INSERT INTO published_news (
                            url, title, source, category, lead_text,
                            raw_text, clean_text, checksum, content_hash, language, domain,
                            extraction_method, published_at, published_date,
                            published_time, published_confidence, published_source,
                            fetched_at, first_seen_at, url_hash, url_normalized, guid, simhash,
                            quality_score, hashtags_ru, hashtags_en
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        url, title, source, category, lead_text,
                        raw_text, clean_text, checksum, content_hash, language, domain,
                        extraction_method, published_at, published_date,
                        published_time, published_confidence, published_source,
                        fetched_at, first_seen_at, url_hash, url_normalized, guid, simhash,
                        quality_score, hashtags_ru, hashtags_en
                    ))
                    self._conn.commit()
                    logger.debug(f"News added: {url}")
                    return cursor.lastrowid
            except sqlite3.IntegrityError:
                logger.debug(f"News already exists: {url}")
                return None
            except sqlite3.OperationalError as oe:
                if 'locked' in str(oe).lower() and attempt < attempts:
                    wait = 0.5 * attempt
                    logger.debug(f"Database locked, retrying in {wait}s (attempt {attempt})")
                    time.sleep(wait)
                    continue
                logger.error(f"OperationalError adding news to DB: {oe}")
                return None
            except Exception as e:
                logger.error(f"Error adding news to DB: {e}")
                return None
    
    def remove_news_by_url(self, url: str) -> bool:
        """
        Удаляет запись новости по URL. Возвращает True если удалена.
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute('DELETE FROM published_news WHERE url = ?', (url,))
                self._conn.commit()
                deleted = cursor.rowcount > 0
                if deleted:
                    logger.debug(f"Removed news from DB: {url}")
                return deleted
        except sqlite3.OperationalError as oe:
            logger.error(f"OperationalError removing news from DB: {oe}")
            return False
        except Exception as e:
            logger.error(f"Error removing news from DB: {e}")
            return False
    
    def is_published(self, url: str) -> bool:
        """Проверяет, была ли новость уже опубликована"""
        try:
            cursor = self._conn.cursor()
            cursor.execute('SELECT 1 FROM published_news WHERE url = ?', (url,))
            result = cursor.fetchone()
            return result is not None
        except Exception as e:
            logger.error(f"Error checking published news: {e}")
            return False

    def is_seen_guid_or_url_hash(self, guid: str | None, url_hash: str | None) -> bool:
        """Check if guid or url_hash was already seen in published_news."""
        if not guid and not url_hash:
            return False
        try:
            cursor = self._conn.cursor()
            if guid and url_hash:
                cursor.execute(
                    'SELECT 1 FROM published_news WHERE guid = ? OR url_hash = ? LIMIT 1',
                    (guid, url_hash)
                )
            elif guid:
                cursor.execute(
                    'SELECT 1 FROM published_news WHERE guid = ? LIMIT 1',
                    (guid,)
                )
            else:
                cursor.execute(
                    'SELECT 1 FROM published_news WHERE url_hash = ? LIMIT 1',
                    (url_hash,)
                )
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking guid/url_hash: {e}")
            return False

    def is_url_normalized_seen(self, url_normalized: str | None) -> bool:
        if not url_normalized:
            return False
        try:
            cursor = self._conn.cursor()
            cursor.execute('SELECT 1 FROM published_news WHERE url_normalized = ? LIMIT 1', (url_normalized,))
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking url_normalized: {e}")
            return False

    def is_checksum_recent(self, checksum: str | None, hours: int = 48) -> bool:
        if not checksum:
            return False
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                f"""
                SELECT 1 FROM published_news
                WHERE checksum = ? AND published_at > datetime('now', '-{int(hours)} hour')
                LIMIT 1
                """,
                (checksum,)
            )
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking checksum: {e}")
            return False

    def is_content_hash_recent(self, content_hash: str | None, hours: int = 48) -> bool:
        if not content_hash:
            return False
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                f"""
                SELECT 1 FROM published_news
                WHERE content_hash = ? AND published_at > datetime('now', '-{int(hours)} hour')
                LIMIT 1
                """,
                (content_hash,)
            )
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking content_hash: {e}")
            return False

    def get_recent_simhashes(self, hours: int = 48, limit: int = 1000) -> List[int]:
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                f"""
                SELECT simhash FROM published_news
                WHERE simhash IS NOT NULL AND published_at > datetime('now', '-{int(hours)} hour')
                ORDER BY published_at DESC
                LIMIT ?
                """,
                (limit,)
            )
            return [row[0] for row in cursor.fetchall() if row and row[0] is not None]
        except Exception as e:
            logger.error(f"Error fetching simhashes: {e}")
            return []
    
    def is_similar_title_published(self, title: str, threshold: float = 0.75) -> bool:
        """Проверяет, есть ли в БД новость с похожим заголовком за последние 24 часа"""
        try:
            # Нормализуем заголовок: убираем знаки препинания, лишние пробелы, переводим в нижний регистр
            import re
            normalized_title = re.sub(r'[^\w\s]', '', title.lower())
            normalized_title = ' '.join(normalized_title.split())
            title_words = set(normalized_title.split())
            
            # Фильтруем стоп-слова (короткие и распространённые)
            stop_words = {'в', 'на', 'из', 'за', 'по', 'до', 'с', 'к', 'у', 'о', 'и', 'а', 'но', 'что', 'как', 'это', 'для'}
            title_words = {w for w in title_words if len(w) > 2 and w not in stop_words}
            
            if len(title_words) < 3:  # Слишком короткий заголовок
                return False
            
            cursor = self._conn.cursor()
            # Получаем заголовки за последние 24 часа
            cursor.execute('''
                SELECT title FROM published_news 
                WHERE published_at > datetime('now', '-1 day')
            ''')
            
            for row in cursor.fetchall():
                existing = re.sub(r'[^\w\s]', '', row[0].lower())
                existing = ' '.join(existing.split())
                existing_words = set(existing.split())
                existing_words = {w for w in existing_words if len(w) > 2 and w not in stop_words}
                
                if len(existing_words) < 3:
                    continue
                
                # Проверяем точное совпадение
                if normalized_title == existing:
                    logger.debug(f"Exact title match found: {title[:50]}")
                    return True
                
                # Проверяем включение (для длинных заголовков)
                if len(normalized_title) > 40:
                    if normalized_title in existing or existing in normalized_title:
                        logger.debug(f"Title substring match: {title[:50]}")
                        return True
                
                # Проверяем процент совпадающих слов (Jaccard similarity)
                common_words = title_words & existing_words
                union_words = title_words | existing_words
                
                if len(union_words) > 0:
                    similarity = len(common_words) / len(union_words)
                    if similarity >= threshold:
                        logger.debug(f"Similar title (words: {similarity:.2f}): {title[:50]}")
                        return True
                        
            return False
        except Exception as e:
            logger.error(f"Error checking similar titles: {e}")
            return False
    
    def get_recent_news(self, limit: int = 100) -> List[Tuple]:
        """Получает последние опубликованные новости"""
        try:
            cursor = self._conn.cursor()
            cursor.execute('''
                SELECT id, url, title, source, category, published_at
                FROM published_news
                ORDER BY published_at DESC
                LIMIT ?
            ''', (limit,))
            results = cursor.fetchall()
            return results
        except Exception as e:
            logger.error(f"Error getting recent news: {e}")
            return []

    def get_news_in_period(self, start_dt: datetime, end_dt: datetime) -> List[dict]:
        """Get published news between start_dt and end_dt (inclusive)."""
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                '''
                      SELECT id, url, title, source, category, lead_text, clean_text,
                          ai_summary, published_at, published_date, published_time, language,
                          hashtags_ru, hashtags_en
                    FROM published_news
                    WHERE datetime(published_at) >= datetime(?)
                      AND datetime(published_at) <= datetime(?)
                    ORDER BY published_at DESC
                ''',
                (start_dt.strftime('%Y-%m-%d %H:%M:%S'), end_dt.strftime('%Y-%m-%d %H:%M:%S'))
            )
            rows = cursor.fetchall()
            results = []
            for row in rows:
                hashtags_ru = row[12] or ""
                hashtags_en = row[13] or ""
                results.append({
                    'id': row[0],
                    'url': row[1],
                    'title': row[2],
                    'source': row[3],
                    'category': row[4],
                    'lead_text': row[5] or "",
                    'clean_text': row[6] or "",
                    'ai_summary': row[7],
                    'published_at': row[8],
                    'published_date': row[9],
                    'published_time': row[10],
                    'language': row[11],
                    'hashtags_ru': hashtags_ru,
                    'hashtags_en': hashtags_en,
                    'hashtags': hashtags_ru or hashtags_en,
                })
            return results
        except Exception as e:
            logger.error(f"Error getting news in period: {e}")
            return []
    
    def get_stats(self) -> dict:
        """Получает статистику БД"""
        try:
            cursor = self._conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM published_news')
            total = cursor.fetchone()[0]
            cursor.execute('''
                SELECT COUNT(*) FROM published_news 
                WHERE published_at > datetime('now', '-1 day')
            ''')
            today = cursor.fetchone()[0]
            return {'total': total, 'today': today}
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {'total': 0, 'today': 0}

    def get_source_counts(self, sources: List[str]) -> dict:
        """Get counts of published news by source."""
        if not sources:
            return {}
        try:
            cursor = self._conn.cursor()
            placeholders = ','.join(['?'] * len(sources))
            cursor.execute(
                f'''SELECT source, COUNT(*)
                    FROM published_news
                    WHERE source IN ({placeholders})
                    GROUP BY source''',
                tuple(sources)
            )
            rows = cursor.fetchall()
            counts = {src: 0 for src in sources}
            for src, cnt in rows:
                counts[src] = cnt or 0
            return counts
        except Exception as e:
            logger.error(f"Error getting source counts: {e}")
            return {src: 0 for src in sources}

    def get_all_sources(self) -> dict:
        """Get all unique sources in DB with their counts (for debugging)."""
        try:
            cursor = self._conn.cursor()
            cursor.execute('''
                SELECT source, COUNT(*)
                FROM published_news
                GROUP BY source
                ORDER BY COUNT(*) DESC
            ''')
            rows = cursor.fetchall()
            return {src: cnt for src, cnt in rows}
        except Exception as e:
            logger.error(f"Error getting all sources: {e}")
            return {}

    def record_source_event(
        self,
        source: str,
        event_type: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        if not source:
            return
        message = (error_message or "").strip() or None
        if message and len(message) > 300:
            message = message[:300]

        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    "INSERT INTO source_events(source, event_type, error_code, created_at) VALUES(?, ?, ?, datetime('now'))",
                    (source, event_type, error_code),
                )
                if event_type == "success":
                    cursor.execute(
                        """
                        INSERT INTO source_health(source, last_success_at, updated_at)
                        VALUES(?, datetime('now'), datetime('now'))
                        ON CONFLICT(source) DO UPDATE SET
                            last_success_at=excluded.last_success_at,
                            updated_at=excluded.updated_at
                        """,
                        (source,),
                    )
                elif event_type == "error":
                    cursor.execute(
                        """
                        INSERT INTO source_health(source, last_error_at, last_error_code, last_error_message, updated_at)
                        VALUES(?, datetime('now'), ?, ?, datetime('now'))
                        ON CONFLICT(source) DO UPDATE SET
                            last_error_at=excluded.last_error_at,
                            last_error_code=excluded.last_error_code,
                            last_error_message=excluded.last_error_message,
                            updated_at=excluded.updated_at
                        """,
                        (source, error_code, message),
                    )
                self._conn.commit()
        except Exception as e:
            logger.debug(f"Error recording source event for {source}: {e}")

    def update_source_quality_fetch(self, source: str, ok: bool, error_code: str | None = None) -> None:
        if not source:
            return
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO source_quality(source, success_count, error_count, last_error_code)
                    VALUES(?, ?, ?, ?)
                    ON CONFLICT(source) DO UPDATE SET
                        success_count = success_count + ?,
                        error_count = error_count + ?,
                        last_error_code = ?,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        source,
                        1 if ok else 0,
                        0 if ok else 1,
                        None if ok else error_code,
                        1 if ok else 0,
                        0 if ok else 1,
                        None if ok else error_code,
                    ),
                )
                self._conn.commit()
        except Exception as e:
            logger.debug(f"Error updating source quality fetch for {source}: {e}")

    def update_source_quality_stats(
        self,
        source: str,
        items_total: int,
        items_new: int,
        items_duplicate: int,
    ) -> None:
        if not source:
            return
        items_total = max(0, int(items_total))
        items_new = max(0, int(items_new))
        items_duplicate = max(0, int(items_duplicate))
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO source_quality(source, items_total, items_new, items_duplicate)
                    VALUES(?, ?, ?, ?)
                    ON CONFLICT(source) DO UPDATE SET
                        items_total = items_total + ?,
                        items_new = items_new + ?,
                        items_duplicate = items_duplicate + ?,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        source,
                        items_total,
                        items_new,
                        items_duplicate,
                        items_total,
                        items_new,
                        items_duplicate,
                    ),
                )
                cursor.execute(
                    """
                    SELECT success_count, error_count, items_total, items_new, items_duplicate
                    FROM source_quality WHERE source = ?
                    """,
                    (source,),
                )
                row = cursor.fetchone() or (0, 0, 0, 0, 0)
                success_count, error_count, total, new, dup = row
                quality_score = self._compute_source_quality_score(success_count, error_count, total, new, dup)
                cursor.execute(
                    """
                    UPDATE source_quality
                    SET quality_score = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE source = ?
                    """,
                    (quality_score, source),
                )
                self._conn.commit()
        except Exception as e:
            logger.debug(f"Error updating source quality stats for {source}: {e}")

    def _compute_source_quality_score(
        self,
        success_count: int,
        error_count: int,
        items_total: int,
        items_new: int,
        items_duplicate: int,
    ) -> float:
        uptime_total = max(0, int(success_count)) + max(0, int(error_count))
        uptime = (success_count / uptime_total) if uptime_total > 0 else 1.0
        dedup_total = max(0, int(items_new)) + max(0, int(items_duplicate))
        uniqueness = (items_new / dedup_total) if dedup_total > 0 else 1.0
        yield_ratio = (items_new / items_total) if items_total > 0 else 0.0
        score = (0.5 * uptime) + (0.3 * uniqueness) + (0.2 * yield_ratio)
        return max(0.0, min(1.0, float(score)))

    def get_source_quality(self, source: str) -> dict | None:
        if not source:
            return None
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT success_count, error_count, items_total, items_new, items_duplicate, quality_score
                FROM source_quality WHERE source = ?
                """,
                (source,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "success_count": row[0] or 0,
                "error_count": row[1] or 0,
                "items_total": row[2] or 0,
                "items_new": row[3] or 0,
                "items_duplicate": row[4] or 0,
                "quality_score": row[5] if row[5] is not None else 0.0,
            }
        except Exception as e:
            logger.debug(f"Error getting source quality for {source}: {e}")
            return None

    def get_source_event_counts(self, sources: List[str], window_hours: int = 24) -> dict:
        if not sources:
            return {}
        try:
            cursor = self._conn.cursor()
            placeholders = ','.join(['?'] * len(sources))
            window = f"-{window_hours} hours"
            cursor.execute(
                f'''
                SELECT source,
                       SUM(CASE WHEN event_type = 'success' THEN 1 ELSE 0 END) AS success_count,
                       SUM(CASE WHEN event_type = 'error' THEN 1 ELSE 0 END) AS error_count,
                       SUM(CASE WHEN event_type = 'drop_old' THEN 1 ELSE 0 END) AS drop_old_count,
                       SUM(CASE WHEN event_type = 'drop_date' THEN 1 ELSE 0 END) AS drop_date_count
                FROM source_events
                WHERE created_at >= datetime('now', ?)
                  AND source IN ({placeholders})
                GROUP BY source
                ''',
                (window, *sources)
            )
            rows = cursor.fetchall()
            counts = {src: {'success_count': 0, 'error_count': 0, 'drop_old_count': 0, 'drop_date_count': 0} for src in sources}
            for source, success_count, error_count, drop_old_count, drop_date_count in rows:
                counts[source] = {
                    'success_count': success_count or 0,
                    'error_count': error_count or 0,
                    'drop_old_count': drop_old_count or 0,
                    'drop_date_count': drop_date_count or 0,
                }
            return counts
        except Exception as e:
            logger.debug(f"Error getting source event counts: {e}")
            return {src: {'success_count': 0, 'error_count': 0, 'drop_old_count': 0, 'drop_date_count': 0} for src in sources}

    def get_source_last_drop_codes(self, sources: List[str], window_hours: int = 24) -> dict:
        if not sources:
            return {}
        try:
            cursor = self._conn.cursor()
            placeholders = ','.join(['?'] * len(sources))
            window = f"-{window_hours} hours"
            cursor.execute(
                f'''
                SELECT e.source, e.error_code
                FROM source_events e
                JOIN (
                    SELECT source, MAX(created_at) AS max_created
                    FROM source_events
                    WHERE created_at >= datetime('now', ?)
                      AND event_type = 'drop_date'
                      AND source IN ({placeholders})
                    GROUP BY source
                ) m
                ON e.source = m.source AND e.created_at = m.max_created
                WHERE e.event_type = 'drop_date'
                ''',
                (window, *sources)
            )
            return {row[0]: row[1] for row in cursor.fetchall()}
        except Exception as e:
            logger.debug(f"Error getting drop-date codes: {e}")
            return {}

    def get_source_health_snapshot(self, sources: List[str]) -> dict:
        if not sources:
            return {}
        try:
            cursor = self._conn.cursor()
            placeholders = ','.join(['?'] * len(sources))
            cursor.execute(
                f'''
                SELECT source, last_success_at, last_error_at, last_error_code, last_error_message
                FROM source_health
                WHERE source IN ({placeholders})
                ''',
                tuple(sources)
            )
            snapshot = {src: {} for src in sources}
            for row in cursor.fetchall():
                snapshot[row[0]] = {
                    'last_success_at': row[1],
                    'last_error_at': row[2],
                    'last_error_code': row[3],
                    'last_error_message': row[4],
                }
            return snapshot
        except Exception as e:
            logger.debug(f"Error getting source health snapshot: {e}")
            return {src: {} for src in sources}

    def get_news_id_by_url(self, url: str) -> int | None:
        """
        Get news ID by URL.
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute('SELECT id FROM published_news WHERE url = ?', (url,))
            result = cursor.fetchone()
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Error getting news id by url: {e}")
            return None

    def get_news_by_id(self, news_id: int) -> dict | None:
        """
        Get news record by id.
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute('''
                  SELECT id, url, title, source, category, lead_text, clean_text, raw_text,
                      checksum, language, domain, extraction_method,
                      ai_summary, ai_summary_created_at, published_at,
                      published_date, published_time, quality_score,
                      hashtags_ru, hashtags_en, url_normalized, simhash
                FROM published_news WHERE id = ?
            ''', (news_id,))
            row = cursor.fetchone()
            if not row:
                return None
            hashtags_ru = row[18] or ""
            hashtags_en = row[19] or ""
            return {
                'id': row[0],
                'url': row[1],
                'title': row[2],
                'source': row[3],
                'category': row[4],
                'lead_text': row[5] or "",
                'clean_text': row[6] or "",
                'raw_text': row[7] or "",
                'checksum': row[8],
                'language': row[9],
                'domain': row[10],
                'extraction_method': row[11],
                'ai_summary': row[12],
                'ai_summary_created_at': row[13],
                'published_at': row[14],
                'published_date': row[15],
                'published_time': row[16],
                'quality_score': row[17],
                'hashtags_ru': hashtags_ru,
                'hashtags_en': hashtags_en,
                'hashtags': hashtags_ru or hashtags_en,
                'url_normalized': row[20],
                'simhash': row[21],
            }
        except Exception as e:
            logger.error(f"Error getting news by id: {e}")
            return None

    def set_telegram_message_id(self, news_id: int, message_id: int) -> bool:
        """Store Telegram message id for a news item."""
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    'UPDATE published_news SET telegram_message_id = ? WHERE id = ?',
                    (message_id, news_id)
                )
                self._conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error setting telegram_message_id: {e}")
            return False
    
    def get_rss_state(self, url: str) -> tuple[str | None, str | None]:
        """
        Get stored ETag and Last-Modified for RSS URL.
        Returns (etag, last_modified) or (None, None) if not found.
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                'SELECT etag, last_modified FROM rss_state WHERE url = ?',
                (url,)
            )
            row = cursor.fetchone()
            return (row[0], row[1]) if row else (None, None)
        except Exception as e:
            logger.debug(f"Error getting RSS state for {url}: {e}")
            return (None, None)
    
    def set_rss_state(self, url: str, etag: str | None, last_modified: str | None) -> bool:
        """
        Store ETag and Last-Modified for RSS URL.
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    '''INSERT INTO rss_state(url, etag, last_modified) VALUES(?, ?, ?)
                       ON CONFLICT(url) DO UPDATE SET etag=excluded.etag, last_modified=excluded.last_modified''',
                    (url, etag, last_modified)
                )
                self._conn.commit()
                return True
        except Exception as e:
            logger.debug(f"Error setting RSS state for {url}: {e}")
            return False

    def cache_rss_items(self, url: str, items: List) -> bool:
        """
        Cache RSS items for potential 304 Not Modified responses.
        """
        try:
            import json
            with self._write_lock:
                cursor = self._conn.cursor()
                items_json = json.dumps(items)
                cursor.execute(
                    '''INSERT INTO rss_cache(url, items, cached_at) VALUES(?, ?, datetime('now'))
                       ON CONFLICT(url) DO UPDATE SET items=excluded.items, cached_at=datetime('now')''',
                    (url, items_json)
                )
                self._conn.commit()
                return True
        except Exception as e:
            logger.debug(f"Error caching RSS items for {url}: {e}")
            return False

    def get_system_setting(self, key: str, default: str | None = None) -> str | None:
        try:
            cursor = self._conn.cursor()
            cursor.execute('SELECT value FROM system_settings WHERE key = ?', (key,))
            row = cursor.fetchone()
            return row[0] if row else default
        except Exception as e:
            logger.debug(f"Error getting system setting {key}: {e}")
            return default

    def set_system_setting(self, key: str, value: str) -> bool:
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    '''INSERT INTO system_settings(key, value) VALUES(?, ?)
                       ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP''',
                    (key, value)
                )
                self._conn.commit()
            return True
        except Exception as e:
            logger.debug(f"Error setting system setting {key}: {e}")
            return False

    def get_source_fetch_state(self, url: str) -> dict | None:
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                '''SELECT url, source_name, next_fetch_at, last_fetch_at, last_status, error_streak, last_error_code
                   FROM source_fetch_state WHERE url = ?''',
                (url,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "url": row[0],
                "source_name": row[1],
                "next_fetch_at": row[2],
                "last_fetch_at": row[3],
                "last_status": row[4],
                "error_streak": row[5] or 0,
                "last_error_code": row[6],
            }
        except Exception as e:
            logger.debug(f"Error getting source fetch state for {url}: {e}")
            return None

    def set_source_fetch_state(
        self,
        url: str,
        source_name: str | None,
        next_fetch_at: float | None,
        last_fetch_at: float | None,
        last_status: str | None,
        error_streak: int | None,
        last_error_code: str | None,
    ) -> bool:
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    '''INSERT INTO source_fetch_state(
                           url, source_name, next_fetch_at, last_fetch_at, last_status, error_streak, last_error_code
                       ) VALUES(?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(url) DO UPDATE SET
                           source_name=excluded.source_name,
                           next_fetch_at=excluded.next_fetch_at,
                           last_fetch_at=excluded.last_fetch_at,
                           last_status=excluded.last_status,
                           error_streak=excluded.error_streak,
                           last_error_code=excluded.last_error_code,
                           updated_at=CURRENT_TIMESTAMP''',
                    (url, source_name, next_fetch_at, last_fetch_at, last_status, error_streak, last_error_code)
                )
                self._conn.commit()
            return True
        except Exception as e:
            logger.debug(f"Error setting source fetch state for {url}: {e}")
            return False

    def get_rss_cached_items(self, url: str) -> List | None:
        """
        Get cached RSS items (for 304 Not Modified responses).
        Returns items if cache is fresh (< 24 hours old), otherwise None.
        """
        try:
            import json
            cursor = self._conn.cursor()
            cursor.execute(
                '''SELECT items FROM rss_cache 
                   WHERE url = ? AND cached_at > datetime('now', '-24 hours')''',
                (url,)
            )
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
            return None
        except Exception as e:
            logger.debug(f"Error getting cached RSS items for {url}: {e}")
            return None

    def get_cached_summary(self, news_id: int) -> str | None:
        """
        Get cached AI summary if exists and not expired (1 hour).
    
        Args:
            news_id: ID of the news article
        
        Returns:
            Summary text or None if not found/expired
        """
        try:
            from config.config import CACHE_EXPIRY_HOURS
    
            cursor = self._conn.cursor()
            query = f"""
                SELECT ai_summary FROM published_news
                WHERE id = ?
                AND ai_summary IS NOT NULL
                AND datetime(ai_summary_created_at) > datetime('now', '-{CACHE_EXPIRY_HOURS} hour')
            """
            cursor.execute(query, (news_id,))
            result = cursor.fetchone()
            return result[0] if result else None
        except Exception as e:
            logger.debug(f"Error getting cached summary for news_id {news_id}: {e}")
            return None

    def acquire_bot_lock(self, instance_id: str, ttl_seconds: int = 600) -> bool:
        """
        Acquire bot instance lock using DB (best-effort).
        Lock expires after ttl_seconds.
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    "SELECT instance_id, locked_at FROM bot_lock WHERE name = ?",
                    ("news_bot",)
                )
                row = cursor.fetchone()
                now = int(time.time())

                if row:
                    existing_instance, locked_at = row[0], row[1]
                    try:
                        locked_at_int = int(locked_at)
                    except Exception:
                        locked_at_int = 0
                    if now - locked_at_int < ttl_seconds:
                        logger.error(
                            f"Bot lock held by {existing_instance}, refusing to start"
                        )
                        return False

                cursor.execute(
                    "INSERT INTO bot_lock(name, instance_id, locked_at) VALUES(?, ?, ?) "
                    "ON CONFLICT(name) DO UPDATE SET instance_id=excluded.instance_id, locked_at=excluded.locked_at",
                    ("news_bot", instance_id, str(now))
                )
                self._conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error acquiring bot lock: {e}")
            return False

    def reset_bot_lock(self) -> None:
        """Force clear bot lock (useful for sandbox restarts)."""
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    "DELETE FROM bot_lock WHERE name = ?",
                    ("news_bot",)
                )
                self._conn.commit()
        except Exception as e:
            logger.debug(f"Error resetting bot lock: {e}")

    def release_bot_lock(self, instance_id: str) -> None:
        """Release bot instance lock if held by instance_id."""
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    "DELETE FROM bot_lock WHERE name = ? AND instance_id = ?",
                    ("news_bot", instance_id)
                )
                self._conn.commit()
        except Exception as e:
            logger.debug(f"Error releasing bot lock: {e}")

    def save_summary(self, news_id: int, summary_text: str) -> bool:
        """
        Save AI summary to cache.
    
        Args:
            news_id: ID of the news article
            summary_text: Summary text to cache
        
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    '''UPDATE published_news
                       SET ai_summary = ?, ai_summary_created_at = CURRENT_TIMESTAMP
                       WHERE id = ?''',
                    (summary_text, news_id)
                )
                self._conn.commit()
                logger.debug(f"Saved summary for news_id {news_id}")
                return True
        except Exception as e:
            logger.error(f"Error saving summary for news_id {news_id}: {e}")
            return False

    def add_ai_usage(self, tokens: int, cost_usd: float, operation_type: str = 'summarize') -> bool:
        """
        Accumulate AI usage totals (persistent across deploys).
        
        Args:
            tokens: Number of tokens used
            cost_usd: Cost in USD
            operation_type: Type of operation ('summarize', 'category', 'text_clean')
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                
                # Update total counters
                base_query = '''
                    UPDATE ai_usage
                    SET total_requests = total_requests + 1,
                        total_tokens = total_tokens + ?,
                        total_cost_usd = total_cost_usd + ?,
                        updated_at = CURRENT_TIMESTAMP
                '''
                
                # Update specific operation counters
                if operation_type == 'summarize':
                    base_query += ''',
                        summarize_requests = summarize_requests + 1,
                        summarize_tokens = summarize_tokens + ?
                    '''
                    cursor.execute(base_query + ' WHERE id = 1', (tokens, cost_usd, tokens))
                elif operation_type == 'category':
                    base_query += ''',
                        category_requests = category_requests + 1,
                        category_tokens = category_tokens + ?
                    '''
                    cursor.execute(base_query + ' WHERE id = 1', (tokens, cost_usd, tokens))
                elif operation_type == 'text_clean':
                    base_query += ''',
                        text_clean_requests = text_clean_requests + 1,
                        text_clean_tokens = text_clean_tokens + ?
                    '''
                    cursor.execute(base_query + ' WHERE id = 1', (tokens, cost_usd, tokens))
                else:
                    # Unknown type, just update totals
                    cursor.execute(base_query + ' WHERE id = 1', (tokens, cost_usd))
                
                self._conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error updating AI usage: {e}")
            return False

    def add_ai_usage_daily(
        self,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
        calls: int = 1,
        cache_hit: bool = False,
    ) -> bool:
        try:
            today = datetime.now().date().isoformat()
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    '''SELECT tokens_in, tokens_out, cost_usd, calls, cache_hits
                       FROM ai_usage_daily WHERE date = ?''',
                    (today,)
                )
                row = cursor.fetchone()
                if row:
                    tokens_in_total = (row[0] or 0) + tokens_in
                    tokens_out_total = (row[1] or 0) + tokens_out
                    cost_total = (row[2] or 0.0) + cost_usd
                    calls_total = (row[3] or 0) + calls
                    cache_hits_total = (row[4] or 0) + (1 if cache_hit else 0)
                    cursor.execute(
                        '''UPDATE ai_usage_daily
                           SET tokens_in = ?, tokens_out = ?, cost_usd = ?, calls = ?, cache_hits = ?,
                               updated_at = CURRENT_TIMESTAMP
                           WHERE date = ?''',
                        (tokens_in_total, tokens_out_total, cost_total, calls_total, cache_hits_total, today)
                    )
                else:
                    cursor.execute(
                        '''INSERT INTO ai_usage_daily(date, tokens_in, tokens_out, cost_usd, calls, cache_hits)
                           VALUES(?, ?, ?, ?, ?, ?)''',
                        (today, tokens_in, tokens_out, cost_usd, calls, 1 if cache_hit else 0)
                    )
                self._conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error updating daily AI usage: {e}")
            return False

    def get_ai_usage_daily(self, date: str | None = None) -> dict:
        try:
            target_date = date or datetime.now().date().isoformat()
            cursor = self._conn.cursor()
            cursor.execute(
                '''SELECT tokens_in, tokens_out, cost_usd, calls, cache_hits
                   FROM ai_usage_daily WHERE date = ?''',
                (target_date,)
            )
            row = cursor.fetchone()
            if not row:
                return {
                    'date': target_date,
                    'tokens_in': 0,
                    'tokens_out': 0,
                    'cost_usd': 0.0,
                    'calls': 0,
                    'cache_hits': 0,
                }
            return {
                'date': target_date,
                'tokens_in': row[0] or 0,
                'tokens_out': row[1] or 0,
                'cost_usd': row[2] or 0.0,
                'calls': row[3] or 0,
                'cache_hits': row[4] or 0,
            }
        except Exception as e:
            logger.error(f"Error getting daily AI usage: {e}")
            return {
                'date': date or datetime.now().date().isoformat(),
                'tokens_in': 0,
                'tokens_out': 0,
                'cost_usd': 0.0,
                'calls': 0,
                'cache_hits': 0,
            }

    def get_ai_usage(self) -> dict:
        """Get comprehensive AI usage totals (persistent)."""
        try:
            cursor = self._conn.cursor()
            cursor.execute('''
                SELECT total_requests, total_tokens, total_cost_usd,
                       summarize_requests, summarize_tokens,
                       category_requests, category_tokens,
                       text_clean_requests, text_clean_tokens
                FROM ai_usage WHERE id = 1
            ''')
            row = cursor.fetchone()
            if not row:
                return {
                    'total_requests': 0, 'total_tokens': 0, 'total_cost_usd': 0.0,
                    'summarize_requests': 0, 'summarize_tokens': 0,
                    'category_requests': 0, 'category_tokens': 0,
                    'text_clean_requests': 0, 'text_clean_tokens': 0
                }
            return {
                'total_requests': row[0] or 0,
                'total_tokens': row[1] or 0,
                'total_cost_usd': row[2] or 0.0,
                'summarize_requests': row[3] or 0,
                'summarize_tokens': row[4] or 0,
                'category_requests': row[5] or 0,
                'category_tokens': row[6] or 0,
                'text_clean_requests': row[7] or 0,
                'text_clean_tokens': row[8] or 0
            }
        except Exception as e:
            logger.error(f"Error getting AI usage: {e}")
            return {
                'total_requests': 0, 'total_tokens': 0, 'total_cost_usd': 0.0,
                'summarize_requests': 0, 'summarize_tokens': 0,
                'category_requests': 0, 'category_tokens': 0,
                'text_clean_requests': 0, 'text_clean_tokens': 0
            }

    def sync_ai_usage_with_deepseek(self, total_requests: int, total_tokens: int, total_cost_usd: float) -> bool:
        """
        Sync AI usage statistics with DeepSeek API data.
        Sets absolute values instead of incrementing.
        
        Args:
            total_requests: Total API requests from DeepSeek
            total_tokens: Total tokens from DeepSeek
            total_cost_usd: Total cost from DeepSeek
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute('''
                    UPDATE ai_usage
                    SET total_requests = ?,
                        total_tokens = ?,
                        total_cost_usd = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                ''', (total_requests, total_tokens, total_cost_usd))
                self._conn.commit()
                logger.info(f"Synced AI usage: {total_requests} requests, {total_tokens} tokens, ${total_cost_usd}")
                return True
        except Exception as e:
            logger.error(f"Error syncing AI usage: {e}")
            return False

    # ==================== BOT SETTINGS (GLOBAL) ====================

    def get_bot_setting(self, key: str, default: str | None = None) -> str | None:
        try:
            cursor = self._conn.cursor()
            cursor.execute('SELECT value FROM bot_settings WHERE key = ?', (key,))
            row = cursor.fetchone()
            return row[0] if row else default
        except Exception as e:
            logger.error(f"Error getting bot setting {key}: {e}")
            return default

    def set_bot_setting(self, key: str, value: str | None) -> bool:
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    '''INSERT OR REPLACE INTO bot_settings (key, value, updated_at)
                       VALUES (?, ?, CURRENT_TIMESTAMP)''',
                    (key, value)
                )
                self._conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error setting bot setting {key}: {e}")
            return False
    # ==================== USER SOURCE SETTINGS ====================
    
    def get_or_create_sources(self, source_list: List[dict]) -> List[int]:
        """
        Убедиться, что все источники есть в таблице sources.
        source_list: [{'code': 'ria', 'title': 'РИА Новости'}, ...]
        Returns: список source_id
        """
        source_ids = []
        with self._write_lock:
            try:
                cursor = self._conn.cursor()
                for src in source_list:
                    cursor.execute(
                        'INSERT OR IGNORE INTO sources (code, title) VALUES (?, ?)',
                        (src['code'], src['title'])
                    )
                    cursor.execute('SELECT id FROM sources WHERE code = ?', (src['code'],))
                    row = cursor.fetchone()
                    if row:
                        source_ids.append(row[0])
                self._conn.commit()
            except Exception as e:
                logger.error(f"Error ensuring sources: {e}")
        return source_ids
    
    def list_sources(self) -> List[dict]:
        """Получить список всех источников"""
        try:
            cursor = self._conn.cursor()
            cursor.execute('SELECT id, code, title, enabled_global FROM sources ORDER BY title')
            return [{'id': r[0], 'code': r[1], 'title': r[2], 'enabled': r[3]} for r in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error listing sources: {e}")
            return []
    
    def get_user_source_enabled_map(self, user_id, env: str = 'prod') -> dict:
        """
        Получить состояние (enabled/disabled) источников для пользователя.
        Returns: {source_id: enabled_bool}
        Если записи нет -> считаем True (по умолчанию включены)
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                '''SELECT source_id, enabled FROM user_source_settings
                   WHERE user_id = ? AND (env = ? OR env IS NULL)''',
                (str(user_id), env)
            )
            return {row[0]: bool(row[1]) for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"Error getting user source map: {e}")
            return {}
    
    def toggle_user_source(self, user_id, source_id: int, env: str = 'prod') -> bool:
        """Переключить состояние источника для пользователя (true <-> false)"""
        with self._write_lock:
            try:
                cursor = self._conn.cursor()
                user_id = str(user_id)
                
                # Получить текущее состояние (по умолчанию True)
                cursor.execute(
                    'SELECT enabled FROM user_source_settings WHERE user_id = ? AND source_id = ? AND (env = ? OR env IS NULL)',
                    (user_id, source_id, env)
                )
                row = cursor.fetchone()
                current_state = row[0] if row else 1  # Default True
                new_state = 1 - current_state
                
                # UPSERT
                cursor.execute(
                          '''INSERT INTO user_source_settings (user_id, source_id, enabled, env)
                              VALUES (?, ?, ?, ?)
                       ON CONFLICT(user_id, source_id) DO UPDATE SET enabled = ?, updated_at = CURRENT_TIMESTAMP''',
                          (user_id, source_id, new_state, env, new_state)
                )
                self._conn.commit()
                return bool(new_state)
            except Exception as e:
                logger.error(f"Error toggling user source: {e}")
                return False
    
    def get_enabled_source_ids_for_user(self, user_id, env: str = 'prod') -> Optional[list]:
        """
        Получить список включенных source_id для пользователя.
        Returns: список ID, или None если все включены (не было отключений)
        """
        try:
            cursor = self._conn.cursor()
            user_id = str(user_id)
            
            # Проверить, есть ли вообще отключенные
            cursor.execute(
                'SELECT COUNT(*) FROM user_source_settings WHERE user_id = ? AND enabled = 0 AND (env = ? OR env IS NULL)',
                (user_id, env)
            )
            disabled_count = cursor.fetchone()[0]
            
            if disabled_count == 0:
                # Нет отключенных -> все включены (оптимизация)
                return None
            
            # Вернуть список включенных (по умолчанию все включены, кроме явно отключенных)
            cursor.execute(
                'SELECT source_id FROM user_source_settings WHERE user_id = ? AND enabled = 0 AND (env = ? OR env IS NULL)',
                (user_id, env)
            )
            disabled_ids = {row[0] for row in cursor.fetchall()}
            
            cursor.execute('SELECT id FROM sources')
            all_ids = {row[0] for row in cursor.fetchall()}
            
            enabled_ids = list(all_ids - disabled_ids)
            return enabled_ids
        except Exception as e:
            logger.error(f"Error getting enabled sources: {e}")
            return None

    def get_feature_flag(self, user_id: str, key: str, default: str = None) -> Optional[str]:
        """
        Получить значение feature flag для пользователя.
        Returns: значение (строка) или default если не установлен
        """
        try:
            cursor = self._conn.cursor()
            user_id = str(user_id)
            cursor.execute(
                'SELECT value FROM feature_flags WHERE user_id = ? AND key = ?',
                (user_id, key)
            )
            row = cursor.fetchone()
            return row[0] if row else default
        except Exception as e:
            logger.error(f"Error getting feature flag: {e}")
            return default

    def set_feature_flag(self, user_id: str, key: str, value: str) -> bool:
        """
        Установить значение feature flag для пользователя.
        Returns: True если успешно, False если ошибка
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                user_id = str(user_id)
                cursor.execute(
                    'INSERT OR REPLACE INTO feature_flags (user_id, key, value, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)',
                    (user_id, key, value)
                )
                self._conn.commit()
                logger.debug(f"Set feature flag: {user_id}.{key} = {value}")
                return True
        except Exception as e:
            logger.error(f"Error setting feature flag: {e}")
            return False
    def add_user_selection(self, user_id: str, news_id: int, env: str = 'prod') -> bool:
        """
        Добавить новость в выбранные пользователем.
        Returns: True если успешно, False если ошибка
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                user_id = str(user_id)
                cursor.execute(
                    'INSERT OR IGNORE INTO user_news_selections (user_id, news_id, env, selected_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)',
                    (user_id, news_id, env)
                )
                self._conn.commit()
                logger.debug(f"Added selection: user={user_id}, news_id={news_id}")
                return True
        except Exception as e:
            logger.error(f"Error adding selection: {e}")
            return False

    def remove_user_selection(self, user_id: str, news_id: int, env: str = 'prod') -> bool:
        """
        Удалить новость из выбранных пользователем.
        Returns: True если успешно, False если ошибка
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                user_id = str(user_id)
                cursor.execute(
                    'DELETE FROM user_news_selections WHERE user_id = ? AND news_id = ? AND (env = ? OR env IS NULL)',
                    (user_id, news_id, env)
                )
                self._conn.commit()
                logger.debug(f"Removed selection: user={user_id}, news_id={news_id}")
                return True
        except Exception as e:
            logger.error(f"Error removing selection: {e}")
            return False

    def get_user_selections(self, user_id: str, env: str = 'prod') -> List[int]:
        """
        Получить список ID новостей, выбранных пользователем.
        Returns: список news_id
        """
        try:
            cursor = self._conn.cursor()
            user_id = str(user_id)
            cursor.execute(
                    '''SELECT news_id FROM user_news_selections
                       WHERE user_id = ? AND (env = ? OR env IS NULL)
                       ORDER BY selected_at DESC''',
                    (user_id, env)
            )
            return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting user selections: {e}")
            return []

    def clear_user_selections(self, user_id: str, env: str = 'prod') -> bool:
        """
        Очистить все выбранные новости пользователя.
        Returns: True если успешно, False если ошибка
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                user_id = str(user_id)
                cursor.execute(
                    'DELETE FROM user_news_selections WHERE user_id = ? AND (env = ? OR env IS NULL)',
                    (user_id, env)
                )
                self._conn.commit()
                logger.debug(f"Cleared selections for user={user_id}")
                return True
        except Exception as e:
            logger.error(f"Error clearing selections: {e}")
            return False

    def is_news_selected(self, user_id: str, news_id: int, env: str = 'prod') -> bool:
        """
        Проверить, выбрана ли новость пользователем.
        Returns: True если выбрана, False если нет
        """
        try:
            cursor = self._conn.cursor()
            user_id = str(user_id)
            cursor.execute(
                    'SELECT 1 FROM user_news_selections WHERE user_id = ? AND news_id = ? AND (env = ? OR env IS NULL) LIMIT 1',
                    (user_id, news_id, env)
            )
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking selection: {e}")
            return False

    def create_invite(self, created_by: str, invite_label: str | None = None) -> Optional[str]:
        """
        Создать новый инвайт-код.
        Returns: код инвайта или None при ошибке
        """
        try:
            import secrets
            code = secrets.token_urlsafe(12)  # Генерируем случайный код
            
            with self._write_lock:
                cursor = self._conn.cursor()
                created_by = str(created_by)
                cleaned_label = invite_label.strip() if invite_label else None
                cursor.execute(
                    'INSERT INTO invites (code, created_by, invite_label) VALUES (?, ?, ?)',
                    (code, created_by, cleaned_label)
                )
                self._conn.commit()
                logger.info(f"Created invite code: {code} by user {created_by}")
                return code
        except Exception as e:
            logger.error(f"Error creating invite: {e}")
            return None

    def create_invite_with_code(self, code: str, created_by: str, invite_label: str | None = None) -> bool:
        """
        Создать новый инвайт-код с заданным значением.
        Returns: True если успешно, False при ошибке
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                created_by = str(created_by)
                cleaned_label = invite_label.strip() if invite_label else None
                cursor.execute(
                    'INSERT INTO invites (code, created_by, invite_label) VALUES (?, ?, ?)',
                    (code, created_by, cleaned_label)
                )
                self._conn.commit()
                logger.info(f"Created invite code (custom): {code} by user {created_by}")
                return True
        except Exception as e:
            logger.error(f"Error creating invite with code: {e}")
            return False

    def use_invite(self, code: str, user_id: str, username: str = None, first_name: str = None) -> bool:
        """
        Использовать инвайт-код для доступа к боту.
        Returns: True если успешно, False если код неверный или уже использован
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                user_id = str(user_id)
                
                # Проверить, что код существует и не использован
                cursor.execute(
                    'SELECT created_by, used_by, invite_label FROM invites WHERE code = ?',
                    (code,)
                )
                row = cursor.fetchone()
                
                if not row:
                    logger.warning(f"Invite code not found: {code}")
                    return False
                
                created_by, used_by, invite_label = row
                
                if used_by:
                    logger.warning(f"Invite code already used: {code} by {used_by}")
                    return False
                
                # Отметить код как использованный
                cursor.execute(
                    'UPDATE invites SET used_by = ?, used_at = CURRENT_TIMESTAMP WHERE code = ?',
                    (user_id, code)
                )
                
                # Добавить пользователя в approved_users
                cursor.execute(
                    'INSERT OR REPLACE INTO approved_users (user_id, username, first_name, invited_by, invite_label) VALUES (?, ?, ?, ?, ?)',
                    (user_id, username, first_name, created_by, invite_label)
                )
                
                self._conn.commit()
                logger.info(f"User {user_id} approved via invite {code}")
                return True
        except Exception as e:
            logger.error(f"Error using invite: {e}")
            return False

    def use_signed_invite(self, code: str, user_id: str, username: str = None, first_name: str = None, secret: str | None = None) -> bool:
        """
        Использовать подписанный инвайт-код (без необходимости общего хранилища).
        Returns: True если успешно, False если код неверный/уже использован
        """
        if not secret:
            return False
        try:
            import hmac
            import hashlib

            if '-' not in code:
                return False

            payload, sig = code.rsplit('-', 1)
            expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:10]
            if not hmac.compare_digest(sig, expected):
                logger.warning(f"Signed invite invalid signature: {code}")
                return False

            with self._write_lock:
                cursor = self._conn.cursor()
                user_id = str(user_id)

                # If already used, reject
                cursor.execute('SELECT used_by, invite_label FROM invites WHERE code = ?', (code,))
                row = cursor.fetchone()
                invite_label = row[1] if row else None
                if row and row[0]:
                    logger.warning(f"Signed invite already used: {code} by {row[0]}")
                    return False

                # Insert invite if not exists and mark as used
                cursor.execute(
                    'INSERT OR IGNORE INTO invites (code, created_by) VALUES (?, ?)',
                    (code, 'SIGNED')
                )
                cursor.execute(
                    'UPDATE invites SET used_by = ?, used_at = CURRENT_TIMESTAMP WHERE code = ?',
                    (user_id, code)
                )

                # Add user to approved_users
                cursor.execute(
                    'INSERT OR REPLACE INTO approved_users (user_id, username, first_name, invited_by, invite_label) VALUES (?, ?, ?, ?, ?)',
                    (user_id, username, first_name, 'SIGNED', invite_label)
                )

                self._conn.commit()
                logger.info(f"User {user_id} approved via signed invite {code}")
                return True
        except Exception as e:
            logger.error(f"Error using signed invite: {e}")
            return False

    def is_user_approved(self, user_id: str) -> bool:
        """
        Проверить, одобрен ли пользователь для доступа к боту.
        Returns: True если одобрен, False если нет
        """
        try:
            cursor = self._conn.cursor()
            user_id = str(user_id)
            cursor.execute(
                'SELECT 1 FROM approved_users WHERE user_id = ? LIMIT 1',
                (user_id,)
            )
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking user approval: {e}")
            return False

    def get_unused_invites(self) -> List[Tuple[str, str, str, str]]:
        """
        Получить список неиспользованных инвайтов.
        Returns: список (code, created_by, created_at)
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                'SELECT code, created_by, created_at, invite_label FROM invites WHERE used_by IS NULL ORDER BY created_at DESC'
            )
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting unused invites: {e}")
            return []

    def get_approved_users(self) -> List[Tuple[str, str, str, str, str, str]]:
        """
        Получить список одобренных пользователей.
        Returns: список (user_id, username, first_name, approved_at)
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                'SELECT user_id, username, first_name, approved_at, invited_by, invite_label FROM approved_users ORDER BY approved_at DESC'
            )
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting approved users: {e}")
            return []

    def block_user(self, user_id: str) -> bool:
        """
        Заблокировать пользователя (удалить из approved_users).
        Returns: True если успешно заблокирован
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute('DELETE FROM approved_users WHERE user_id = ?', (str(user_id),))
                self._conn.commit()
                deleted = cursor.rowcount > 0
                if deleted:
                    logger.info(f"User {user_id} blocked")
                return deleted
        except Exception as e:
            logger.error(f"Error blocking user {user_id}: {e}")
            return False

    def unblock_user(self, user_id: str, username: str = None, first_name: str = None) -> bool:
        """
        Разблокировать пользователя (добавить в approved_users).
        Returns: True если успешно разблокирован
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    'INSERT OR REPLACE INTO approved_users (user_id, username, first_name) VALUES (?, ?, ?)',
                    (str(user_id), username or '', first_name or '')
                )
                self._conn.commit()
                logger.info(f"User {user_id} unblocked")
                return True
        except Exception as e:
            logger.error(f"Error unblocking user {user_id}: {e}")
            return False

    def delete_invite(self, code: str) -> bool:
        """
        Удалить инвайт-код.
        Returns: True если успешно, False если ошибка
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute('DELETE FROM invites WHERE code = ?', (code,))
                self._conn.commit()
                logger.info(f"Deleted invite code: {code}")
                return True
        except Exception as e:
            logger.error(f"Error deleting invite: {e}")
            return False

    def get_invite_label(self, code: str) -> str | None:
        """Получить имя/метку инвайта по коду."""
        try:
            cursor = self._conn.cursor()
            cursor.execute('SELECT invite_label FROM invites WHERE code = ?', (code,))
            row = cursor.fetchone()
            return row[0] if row and row[0] else None
        except Exception as e:
            logger.error(f"Error getting invite label: {e}")
            return None

    def get_translation_cache(self, news_id: int, checksum: str, target_lang: str) -> str | None:
        """Get cached translation by news_id, checksum, and target language."""
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                '''SELECT translated_text FROM translation_cache_v2
                   WHERE news_id = ? AND checksum = ? AND target_lang = ?''',
                (int(news_id), checksum, target_lang)
            )
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.error(f"Error getting translation cache: {e}")
            return None

    def set_translation_cache(self, news_id: int, checksum: str, target_lang: str, translated_text: str) -> bool:
        """Store translation in cache by news_id, checksum, and target language."""
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    '''INSERT OR REPLACE INTO translation_cache_v2
                       (news_id, checksum, target_lang, translated_text)
                       VALUES (?, ?, ?, ?)''',
                    (int(news_id), checksum, target_lang, translated_text)
                )
                self._conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error setting translation cache: {e}")
            return False

    def set_user_translation(self, user_id: str, enabled: bool, target_lang: str = 'ru', env: str = 'prod') -> bool:
        """Set translation preference for a user."""
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    '''INSERT INTO user_preferences (user_id, env, translate_enabled, translate_lang, updated_at)
                       VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                       ON CONFLICT(user_id) DO UPDATE SET
                         translate_enabled = excluded.translate_enabled,
                         translate_lang = excluded.translate_lang,
                         env = excluded.env,
                         updated_at = CURRENT_TIMESTAMP''',
                    (str(user_id), env, 1 if enabled else 0, target_lang)
                )
                self._conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error setting user translation: {e}")
            return False

    def get_user_translation(self, user_id: str, env: str = 'prod') -> tuple[bool, str]:
        """Return (translate_enabled, translate_lang) for user."""
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                '''SELECT translate_enabled, translate_lang
                   FROM user_preferences
                   WHERE user_id = ? AND (env = ? OR env IS NULL)''',
                (str(user_id), env)
            )
            row = cursor.fetchone()
            if not row:
                return False, 'ru'
            return bool(row[0]), (row[1] or 'ru')
        except Exception as e:
            logger.error(f"Error getting user translation: {e}")
            return False, 'ru'

    def set_user_category_filter(self, user_id: str, category: str | None, env: str = 'prod') -> bool:
        """Set per-user category filter (prod only)."""
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    '''INSERT INTO user_preferences (user_id, env, category_filter, updated_at)
                       VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                       ON CONFLICT(user_id) DO UPDATE SET
                         category_filter = excluded.category_filter,
                         env = excluded.env,
                         updated_at = CURRENT_TIMESTAMP''',
                    (str(user_id), env, category)
                )
                self._conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error setting user category filter: {e}")
            return False

    def get_user_category_filter(self, user_id: str, env: str = 'prod') -> str | None:
        """Get per-user category filter (prod only)."""
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                '''SELECT category_filter
                   FROM user_preferences
                   WHERE user_id = ? AND (env = ? OR env IS NULL)''',
                (str(user_id), env)
            )
            row = cursor.fetchone()
            return row[0] if row and row[0] else None
        except Exception as e:
            logger.error(f"Error getting user category filter: {e}")
            return None
    def set_user_paused(self, user_id: str, is_paused: bool, env: str = 'prod') -> bool:
        """
        Установить состояние паузы для пользователя.
        Returns: True если успешно, False если ошибка
        """
        return self.set_pause_state(user_id, is_paused, env=env)

    def is_user_paused(self, user_id: str, env: str = 'prod') -> bool:
        """
        Проверить, приостановлены ли новости для пользователя.
        Returns: True если приостановлены, False если нет
        """
        try:
            cursor = self._conn.cursor()
            user_id = str(user_id)
            cursor.execute(
                'SELECT is_paused FROM user_preferences WHERE user_id = ? AND (env = ? OR env IS NULL)',
                (user_id, env)
            )
            row = cursor.fetchone()
            return row[0] == 1 if row else False
        except Exception as e:
            logger.error(f"Error checking user paused: {e}")
            return False

    # Global collection control methods
    def set_collection_stopped(self, stopped: bool) -> bool:
        """Set global collection stopped state"""
        try:
            with self._lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    '''INSERT OR REPLACE INTO bot_settings (key, value, updated_at)
                       VALUES ('collection_stopped', ?, CURRENT_TIMESTAMP)''',
                    ('1' if stopped else '0',)
                )
                cursor.execute('''
                    INSERT OR REPLACE INTO system_settings (setting_key, setting_value, updated_at)
                    VALUES ('collection_stopped', ?, CURRENT_TIMESTAMP)
                ''', ('1' if stopped else '0',))
                self._conn.commit()
            logger.info(f"Collection stopped state set to: {stopped}")
            return True
        except Exception as e:
            logger.error(f"Error setting collection stopped: {e}")
            return False

    def is_collection_stopped(self) -> bool:
        """Check if collection is globally stopped"""
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                'SELECT value FROM bot_settings WHERE key = ?',
                ('collection_stopped',)
            )
            row = cursor.fetchone()
            if row is not None:
                return row[0] == '1'
            cursor.execute(
                'SELECT setting_value FROM system_settings WHERE setting_key = ?',
                ('collection_stopped',)
            )
            result = cursor.fetchone()
            return result[0] == '1' if result else False
        except Exception as e:
            logger.error(f"Error checking collection stopped: {e}")
            return False

    def get_delivery_state(self, user_id: str, env: str = 'prod') -> dict:
        """Get delivery state for a user from DB."""
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                '''SELECT is_paused, paused_at, resume_at, last_delivered_news_id, pause_version
                   FROM user_preferences WHERE user_id = ? AND (env = ? OR env IS NULL)''',
                (str(user_id), env)
            )
            row = cursor.fetchone()
            if not row:
                return {
                    'is_paused': False,
                    'paused_at': None,
                    'resume_at': None,
                    'last_delivered_news_id': None,
                    'pause_version': 0,
                }
            return {
                'is_paused': bool(row[0]),
                'paused_at': row[1],
                'resume_at': row[2],
                'last_delivered_news_id': row[3],
                'pause_version': row[4] or 0,
            }
        except Exception as e:
            logger.error(f"Error getting delivery state: {e}")
            return {
                'is_paused': False,
                'paused_at': None,
                'resume_at': None,
                'last_delivered_news_id': None,
                'pause_version': 0,
            }

    def set_pause_state(self, user_id: str, is_paused: bool, env: str = 'prod') -> bool:
        """Set pause/resume state with pause_version increment."""
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                user_id = str(user_id)
                if is_paused:
                    cursor.execute(
                                                '''INSERT INTO user_preferences (user_id, env, is_paused, paused_at, pause_version, updated_at)
                                                     VALUES (?, ?, 1, CURRENT_TIMESTAMP, 1, CURRENT_TIMESTAMP)
                           ON CONFLICT(user_id) DO UPDATE SET
                             is_paused = 1,
                             paused_at = CURRENT_TIMESTAMP,
                                                         env = excluded.env,
                             pause_version = pause_version + 1,
                             updated_at = CURRENT_TIMESTAMP''',
                                                (user_id, env)
                    )
                else:
                    cursor.execute(
                                                '''INSERT INTO user_preferences (user_id, env, is_paused, resume_at, pause_version, updated_at)
                                                     VALUES (?, ?, 0, CURRENT_TIMESTAMP, 1, CURRENT_TIMESTAMP)
                           ON CONFLICT(user_id) DO UPDATE SET
                             is_paused = 0,
                             resume_at = CURRENT_TIMESTAMP,
                                                         env = excluded.env,
                             pause_version = pause_version + 1,
                             updated_at = CURRENT_TIMESTAMP''',
                                                (user_id, env)
                    )
                self._conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error setting pause state: {e}")
            return False

    def update_last_delivered(self, user_id: str, news_id: int, env: str = 'prod') -> bool:
        """Update last delivered news id for a user."""
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                                        '''INSERT INTO user_preferences (user_id, env, last_delivered_news_id, updated_at)
                                             VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                       ON CONFLICT(user_id) DO UPDATE SET
                         last_delivered_news_id = ?,
                                                 env = excluded.env,
                         updated_at = CURRENT_TIMESTAMP''',
                                        (str(user_id), env, news_id, news_id)
                )
                self._conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating last delivered: {e}")
            return False

    def try_log_delivery(self, user_id: str, news_id: int) -> bool:
        """Insert delivery log row. Returns True if inserted, False if duplicate."""
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    'INSERT OR IGNORE INTO delivery_log (user_id, news_id) VALUES (?, ?)',
                    (str(user_id), int(news_id))
                )
                self._conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error logging delivery: {e}")
            return False

    def remove_delivery_log(self, user_id: str, news_id: int) -> bool:
        """Remove delivery log row (e.g., on send failure)."""
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    'DELETE FROM delivery_log WHERE user_id = ? AND news_id = ?',
                    (str(user_id), int(news_id))
                )
                self._conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error removing delivery log: {e}")
            return False

    def get_news_after_id(self, last_id: int | None, limit: int = 50) -> List[dict]:
        """Get news items with id > last_id ordered by id ascending."""
        try:
            cursor = self._conn.cursor()
            if last_id is None:
                cursor.execute(
                    '''SELECT id, url, title, source, category, lead_text, clean_text,
                              ai_summary, published_at, published_date, published_time,
                              hashtags_ru, hashtags_en
                       FROM published_news ORDER BY id ASC LIMIT ?''',
                    (limit,)
                )
            else:
                cursor.execute(
                    '''SELECT id, url, title, source, category, lead_text, clean_text,
                              ai_summary, published_at, published_date, published_time,
                              hashtags_ru, hashtags_en
                       FROM published_news WHERE id > ? ORDER BY id ASC LIMIT ?''',
                    (int(last_id), limit)
                )
            rows = cursor.fetchall()
            results = []
            for row in rows:
                hr, he = row[11] or "", row[12] or ""
                results.append({
                    'id': row[0],
                    'url': row[1],
                    'title': row[2],
                    'source': row[3],
                    'category': row[4],
                    'lead_text': row[5] or "",
                    'clean_text': row[6] or "",
                    'ai_summary': row[7],
                    'published_at': row[8],
                    'published_date': row[9],
                    'published_time': row[10],
                    'hashtags_ru': hr,
                    'hashtags_en': he,
                    'hashtags': hr or he,
                })
            return results
        except Exception as e:
            logger.error(f"Error getting news after id: {e}")
            return []

    def close(self) -> None:
        """Close the database connection."""
        try:
            self._conn.close()
        except Exception as e:
            logger.debug(f"Error closing database: {e}")