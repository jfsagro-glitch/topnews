# LLM Cache and Budget Management additions for database.py

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Add these methods to NewsDatabase class:

def get_llm_cache(self, cache_key: str) -> Optional[dict]:
    """
    Get cached LLM response by key.
    
    Args:
        cache_key: MD5 hash of (task_type + title + text)
        
    Returns:
        Cached response dict or None if not found/expired
    """
    try:
        cursor = self._conn.cursor()
        cursor.execute('''
            SELECT response_json, input_tokens, output_tokens, task_type
            FROM llm_cache
            WHERE cache_key = ? AND expires_at > CURRENT_TIMESTAMP
        ''', (cache_key,))
        row = cursor.fetchone()
        if row:
            import json
            return {
                'response': json.loads(row[0]),
                'input_tokens': row[1],
                'output_tokens': row[2],
                'task_type': row[3],
                'cache_hit': True
            }
        return None
    except Exception as e:
        logger.debug(f"Error getting LLM cache: {e}")
        return None

def set_llm_cache(self, cache_key: str, task_type: str, response: dict, 
                  input_tokens: int, output_tokens: int, ttl_hours: int = 72):
    """
    Store LLM response in cache.
    
    Args:
        cache_key: MD5 hash of (task_type + title + text)
        task_type: 'summarize', 'category', 'text_clean'
        response: Response dict from LLM
        input_tokens: Input token count
        output_tokens: Output token count
        ttl_hours: Time to live in hours (default 72)
    """
    try:
        import json
        from datetime import datetime, timedelta
        
        expires_at = (datetime.now() + timedelta(hours=ttl_hours)).isoformat()
        response_json = json.dumps(response, ensure_ascii=False)
        
        with self._write_lock:
            cursor = self._conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO llm_cache 
                (cache_key, task_type, response_json, input_tokens, output_tokens, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (cache_key, task_type, response_json, input_tokens, output_tokens, expires_at))
            self._conn.commit()
            logger.debug(f"Cached LLM response: {task_type}, key={cache_key[:16]}...")
    except Exception as e:
        logger.debug(f"Error setting LLM cache: {e}")

def _cleanup_expired_cache(self):
    """Remove expired LLM cache entries"""
    try:
        with self._write_lock:
            cursor = self._conn.cursor()
            cursor.execute('''
                DELETE FROM llm_cache WHERE expires_at < CURRENT_TIMESTAMP
            ''')
            deleted = cursor.rowcount
            self._conn.commit()
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} expired LLM cache entries")
    except Exception as e:
        logger.debug(f"Error cleaning LLM cache: {e}")

def get_daily_llm_cost(self) -> float:
    """Get today's LLM cost in USD"""
    try:
        from datetime import datetime
        today = datetime.now().date().isoformat()
        
        cursor = self._conn.cursor()
        cursor.execute('''
            SELECT daily_cost_usd, daily_cost_date FROM ai_usage WHERE id = 1
        ''')
        row = cursor.fetchone()
        if row and row[1] == today:
            return row[0] or 0.0
        return 0.0
    except Exception as e:
        logger.debug(f"Error getting daily LLM cost: {e}")
        return 0.0

def add_daily_llm_cost(self, cost_usd: float):
    """Add to today's LLM cost"""
    try:
        from datetime import datetime
        today = datetime.now().date().isoformat()
        
        with self._write_lock:
            cursor = self._conn.cursor()
            # Get current daily cost
            cursor.execute('SELECT daily_cost_usd, daily_cost_date FROM ai_usage WHERE id = 1')
            row = cursor.fetchone()
            
            if row and row[1] == today:
                new_cost = (row[0] or 0.0) + cost_usd
            else:
                # New day, reset
                new_cost = cost_usd
            
            cursor.execute('''
                UPDATE ai_usage
                SET daily_cost_usd = ?,
                    daily_cost_date = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            ''', (new_cost, today))
            self._conn.commit()
    except Exception as e:
        logger.debug(f"Error adding daily LLM cost: {e}")

def get_cache_stats(self) -> dict:
    """Get LLM cache statistics"""
    try:
        cursor = self._conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN expires_at > CURRENT_TIMESTAMP THEN 1 ELSE 0 END) as active,
                   SUM(CASE WHEN expires_at <= CURRENT_TIMESTAMP THEN 1 ELSE 0 END) as expired
            FROM llm_cache
        ''')
        row = cursor.fetchone()
        if row:
            return {'total': row[0], 'active': row[1], 'expired': row[2]}
        return {'total': 0, 'active': 0, 'expired': 0}
    except Exception as e:
        logger.debug(f"Error getting cache stats: {e}")
        return {'total': 0, 'active': 0, 'expired': 0}
