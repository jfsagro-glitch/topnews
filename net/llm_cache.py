"""
LLM Cache manager for TopNews bot.
Provides hash-based caching for all LLM API calls to reduce costs.
"""
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class LLMCacheManager:
    """Manager for LLM response caching with SQLite backend"""
    
    def __init__(self, db):
        """
        Initialize cache manager.
        
        Args:
            db: NewsDatabase instance
        """
        self.db = db
        self._ensure_cache_table()
        self._hits = 0
        self._misses = 0
    
    def _ensure_cache_table(self):
        """Ensure llm_cache table exists"""
        try:
            cursor = self.db._conn.cursor()
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
            
            # Add daily budget tracking columns if not exist
            cursor.execute("PRAGMA table_info(ai_usage)")
            columns = {row[1] for row in cursor.fetchall()}
            if 'daily_cost_usd' not in columns:
                cursor.execute('ALTER TABLE ai_usage ADD COLUMN daily_cost_usd REAL DEFAULT 0.0')
            if 'daily_cost_date' not in columns:
                cursor.execute('ALTER TABLE ai_usage ADD COLUMN daily_cost_date TEXT')
            
            self.db._conn.commit()
            logger.debug("LLM cache table initialized")
        except Exception as e:
            logger.warning(f"Error ensuring cache table: {e}")
    
    @staticmethod
    def generate_cache_key(task_type: str, title: str, text: str, **kwargs) -> str:
        """
        Generate cache key from task inputs.
        
        Args:
            task_type: 'summarize', 'category', 'text_clean'
            title: Article title
            text: Article text
            **kwargs: Additional parameters (e.g., current_category for verify_category)
            
        Returns:
            MD5 hash as hex string
        """
        # Normalize inputs
        title_norm = (title or '').strip().lower()
        text_norm = (text or '').strip().lower()

        # Allow checksum-based caching (preferred for large texts)
        checksum = kwargs.pop('checksum', None)

        # Include kwargs in key for tasks that depend on them
        kwargs_str = json.dumps(sorted(kwargs.items()), ensure_ascii=False)

        # Generate hash
        if checksum:
            content = f"{task_type}|{checksum}|{kwargs_str}"
        else:
            content = f"{task_type}|{title_norm}|{text_norm}|{kwargs_str}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        Get cached LLM response.
        
        Args:
            cache_key: Cache key from generate_cache_key()
            
        Returns:
            Cached response dict or None if not found/expired
        """
        try:
            cursor = self.db._conn.cursor()
            cursor.execute('''
                SELECT response_json, input_tokens, output_tokens, task_type
                FROM llm_cache
                WHERE cache_key = ? AND expires_at > CURRENT_TIMESTAMP
            ''', (cache_key,))
            row = cursor.fetchone()
            
            if row:
                logger.debug(f"LLM cache HIT: {cache_key[:16]}...")
                self._hits += 1
                return {
                    'response': json.loads(row[0]),
                    'input_tokens': row[1],
                    'output_tokens': row[2],
                    'task_type': row[3],
                    'cache_hit': True
                }
            
            logger.debug(f"LLM cache MISS: {cache_key[:16]}...")
            self._misses += 1
            return None
        except Exception as e:
            logger.debug(f"Error getting LLM cache: {e}")
            return None
    
    def set(self, cache_key: str, task_type: str, response: Any, 
            input_tokens: int, output_tokens: int, ttl_hours: int = 72):
        """
        Store LLM response in cache.
        
        Args:
            cache_key: Cache key from generate_cache_key()
            task_type: 'summarize', 'category', 'text_clean'
            response: Response from LLM (will be JSON-serialized)
            input_tokens: Input token count
            output_tokens: Output token count
            ttl_hours: Time to live in hours (default 72)
        """
        try:
            expires_at = (datetime.now() + timedelta(hours=ttl_hours)).isoformat()
            response_json = json.dumps(response, ensure_ascii=False)
            
            with self.db._write_lock:
                cursor = self.db._conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO llm_cache 
                    (cache_key, task_type, response_json, input_tokens, output_tokens, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (cache_key, task_type, response_json, input_tokens, output_tokens, expires_at))
                self.db._conn.commit()
                logger.debug(f"Cached LLM response: {task_type}, key={cache_key[:16]}...")
        except Exception as e:
            logger.debug(f"Error setting LLM cache: {e}")
    
    def cleanup_expired(self):
        """Remove expired cache entries"""
        try:
            with self.db._write_lock:
                cursor = self.db._conn.cursor()
                cursor.execute('DELETE FROM llm_cache WHERE expires_at < CURRENT_TIMESTAMP')
                deleted = cursor.rowcount
                self.db._conn.commit()
                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} expired LLM cache entries")
        except Exception as e:
            logger.debug(f"Error cleaning LLM cache: {e}")
    
    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics (size and status)"""
        try:
            cursor = self.db._conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN expires_at > CURRENT_TIMESTAMP THEN 1 ELSE 0 END) as active,
                       SUM(CASE WHEN expires_at <= CURRENT_TIMESTAMP THEN 1 ELSE 0 END) as expired
                FROM llm_cache
            ''')
            row = cursor.fetchone()
            if row:
                return {
                    'size': row[1] or 0,  # Active entries
                    'total': row[0] or 0,
                    'expired': row[2] or 0,
                    'hits': self._hits,
                    'misses': self._misses
                }
            return {'size': 0, 'total': 0, 'expired': 0, 'hits': self._hits, 'misses': self._misses}
        except Exception as e:
            logger.debug(f"Error getting cache stats: {e}")
            return {'size': 0, 'total': 0, 'expired': 0, 'hits': self._hits, 'misses': self._misses}


class BudgetGuard:
    """Manages daily LLM budget limits"""
    
    def __init__(self, db, daily_limit_usd: float = 1.0, daily_limit_tokens: int = 0):
        """
        Initialize budget guard.
        
        Args:
            db: NewsDatabase instance
            daily_limit_usd: Daily budget limit in USD
        """
        self.db = db
        self.daily_limit_usd = daily_limit_usd
        self.daily_limit_tokens = daily_limit_tokens
    
    def get_daily_cost(self) -> float:
        """Get today's LLM cost in USD"""
        try:
            daily = self.db.get_ai_usage_daily()
            return daily.get('cost_usd', 0.0) or 0.0
        except Exception as e:
            logger.debug(f"Error getting daily cost: {e}")
            return 0.0

    def get_daily_tokens(self) -> int:
        try:
            daily = self.db.get_ai_usage_daily()
            return int((daily.get('tokens_in', 0) or 0) + (daily.get('tokens_out', 0) or 0))
        except Exception as e:
            logger.debug(f"Error getting daily tokens: {e}")
            return 0
    
    def add_cost(self, cost_usd: float):
        """Add to today's cost (legacy wrapper)."""
        try:
            self.db.add_ai_usage_daily(tokens_in=0, tokens_out=0, cost_usd=cost_usd, calls=0)
            if self.daily_limit_usd > 0:
                new_cost = self.get_daily_cost()
                if new_cost >= self.daily_limit_usd * 0.9:
                    logger.warning(
                        f"⚠️ Daily LLM budget at {new_cost/self.daily_limit_usd*100:.1f}% "
                        f"(${new_cost:.4f}/${self.daily_limit_usd})"
                    )
        except Exception as e:
            logger.debug(f"Error adding cost: {e}")
    
    def can_make_request(self, tokens_estimate: int = 0) -> bool:
        """Check if request is within budget"""
        current = self.get_daily_cost()
        if self.daily_limit_usd > 0 and current >= self.daily_limit_usd:
            logger.warning(f"❌ Daily LLM budget exceeded: ${current:.4f} >= ${self.daily_limit_usd}")
            return False
        if self.daily_limit_tokens > 0:
            current_tokens = self.get_daily_tokens()
            if current_tokens + max(0, tokens_estimate) >= self.daily_limit_tokens:
                logger.warning(
                    f"❌ Daily LLM token budget exceeded: {current_tokens} >= {self.daily_limit_tokens}"
                )
                return False
        return True
    
    def is_economy_mode(self) -> bool:
        """Check if should use economy mode (>80% budget)"""
        if self.daily_limit_usd <= 0:
            return False
        current = self.get_daily_cost()
        return current >= (self.daily_limit_usd * 0.8)
