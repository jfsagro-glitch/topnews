"""
AI Level Management Service (replaces boolean feature_flags with integer levels 0-5)
Provides unified interface for getting/setting AI module levels
Handles migration from old boolean flags to new integer levels
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Default AI levels from environment or hardcoded defaults
AI_HASHTAGS_LEVEL_DEFAULT = int(os.getenv('AI_HASHTAGS_LEVEL_DEFAULT', '3'))
AI_CLEANUP_LEVEL_DEFAULT = int(os.getenv('AI_CLEANUP_LEVEL_DEFAULT', '3'))
AI_SUMMARY_LEVEL_DEFAULT = int(os.getenv('AI_SUMMARY_LEVEL_DEFAULT', '3'))

# Module names for consistency
AI_MODULES = {
    'hashtags': 'ai_hashtags_level',
    'cleanup': 'ai_cleanup_level',
    'summary': 'ai_summary_level',
}


class AILevelManager:
    """Manages AI module levels for users with migration support"""

    def __init__(self, db):
        """
        Initialize with database connection
        Args:
            db: NewsDatabase instance
        """
        self.db = db

    def get_level(self, user_id: str, module: str, default: Optional[int] = None) -> int:
        """
        Get AI level for a specific module (0-5)
        Args:
            user_id: user/admin ID
            module: 'hashtags', 'cleanup', or 'summary'
            default: fallback default (from environment or hardcoded)
        Returns:
            int: level 0-5, clamped to valid range
        """
        user_id = str(user_id)
        
        # Determine default
        if default is None:
            if module == 'hashtags':
                default = AI_HASHTAGS_LEVEL_DEFAULT
            elif module == 'cleanup':
                default = AI_CLEANUP_LEVEL_DEFAULT
            elif module == 'summary':
                default = AI_SUMMARY_LEVEL_DEFAULT
            else:
                default = 3  # fallback
        
        key = AI_MODULES.get(module)
        if not key:
            logger.warning(f"Unknown module: {module}")
            return default
        
        # Try to get from feature_flags
        value_str = self.db.get_feature_flag(user_id, key)
        
        if value_str is not None:
            try:
                level = int(value_str)
                return max(0, min(5, level))  # Clamp to 0-5
            except (ValueError, TypeError):
                logger.warning(f"Invalid level value for {key}: {value_str}")
                return default
        
        # No *_level flag found - try to migrate from old *_enabled flag
        old_key = key.replace('_level', '_enabled')
        old_value_str = self.db.get_feature_flag(user_id, old_key)
        
        if old_value_str is not None:
            try:
                # Migration: enabled=0 -> level=0, enabled=1 -> level=default
                enabled = int(old_value_str) if old_value_str.isdigit() else (1 if old_value_str.lower() in ('true', '1', 'yes') else 0)
                new_level = 0 if enabled == 0 else default
                
                # Soft migration: write new level and optionally clean old flag
                self.set_level(user_id, module, new_level)
                logger.info(f"Migrated {user_id}.{old_key} ({enabled}) -> {key} ({new_level})")
                
                return new_level
            except (ValueError, TypeError):
                logger.warning(f"Invalid old flag value for {old_key}: {old_value_str}")
                return default
        
        # No flags found - return default
        return default

    def set_level(self, user_id: str, module: str, level: int) -> bool:
        """
        Set AI level for a specific module (0-5)
        Args:
            user_id: user/admin ID
            module: 'hashtags', 'cleanup', or 'summary'
            level: 0-5, will be clamped
        Returns:
            bool: True if successful
        """
        user_id = str(user_id)
        level = max(0, min(5, level))  # Clamp to 0-5
        
        key = AI_MODULES.get(module)
        if not key:
            logger.warning(f"Unknown module: {module}")
            return False
        
        return self.db.set_feature_flag(user_id, key, str(level))

    def inc_level(self, user_id: str, module: str) -> int:
        """
        Increment AI level for a module (max 5)
        Returns: new level
        """
        current = self.get_level(user_id, module)
        new_level = min(5, current + 1)
        self.set_level(user_id, module, new_level)
        return new_level

    def dec_level(self, user_id: str, module: str) -> int:
        """
        Decrement AI level for a module (min 0)
        Returns: new level
        """
        current = self.get_level(user_id, module)
        new_level = max(0, current - 1)
        self.set_level(user_id, module, new_level)
        return new_level


def get_llm_profile(level: int, module: str = 'summary') -> dict:
    """
    Get LLM configuration profile based on level (1-5)
    Returns dict with keys: max_tokens, temperature, model, and other params
    
    Args:
        level: 0-5 (0 means disabled, 1-5 = actual profiles)
        module: 'summary', 'hashtags', 'cleanup'
    
    Returns:
        dict: LLM parameters (empty dict if level=0)
    """
    if level == 0:
        return {'disabled': True}
    
    # Ensure level is in range 1-5
    level = max(1, min(5, level))
    
    # Module-specific profiles
    if module == 'summary':
        profiles = {
            1: {
                'model': 'deepseek-chat',
                'max_tokens': 200,
                'temperature': 0.5,
                'top_p': 0.9,
                'description': 'Fast, cheap summary (200 tokens)'
            },
            2: {
                'model': 'deepseek-chat',
                'max_tokens': 300,
                'temperature': 0.6,
                'top_p': 0.95,
                'description': 'Standard summary (300 tokens)'
            },
            3: {
                'model': 'deepseek-chat',
                'max_tokens': 400,
                'temperature': 0.7,
                'top_p': 0.95,
                'description': 'Balanced summary (400 tokens) [DEFAULT]'
            },
            4: {
                'model': 'deepseek-chat',
                'max_tokens': 600,
                'temperature': 0.7,
                'top_p': 0.98,
                'description': 'Detailed summary (600 tokens)'
            },
            5: {
                'model': 'deepseek-chat',
                'max_tokens': 800,
                'temperature': 0.8,
                'top_p': 0.99,
                'description': 'Comprehensive summary (800 tokens) [BEST QUALITY]'
            },
        }
    elif module == 'hashtags':
        profiles = {
            1: {
                'model': 'deepseek-chat',
                'max_tokens': 80,
                'temperature': 0.2,
                'top_p': 0.9,
                'description': 'Fast hashtag generation (80 tokens)'
            },
            2: {
                'model': 'deepseek-chat',
                'max_tokens': 100,
                'temperature': 0.25,
                'top_p': 0.92,
                'description': 'Standard hashtags (100 tokens)'
            },
            3: {
                'model': 'deepseek-chat',
                'max_tokens': 120,
                'temperature': 0.3,
                'top_p': 0.95,
                'description': 'Balanced hashtags (120 tokens) [DEFAULT]'
            },
            4: {
                'model': 'deepseek-chat',
                'max_tokens': 120,
                'temperature': 0.3,
                'top_p': 0.96,
                'description': 'Rich hashtags (120 tokens)'
            },
            5: {
                'model': 'deepseek-chat',
                'max_tokens': 120,
                'temperature': 0.3,
                'top_p': 0.98,
                'description': 'Comprehensive hashtags (120 tokens) [BEST QUALITY]'
            },
        }
    elif module == 'cleanup':
        profiles = {
            1: {
                'model': 'deepseek-chat',
                'max_tokens': 150,
                'temperature': 0.2,
                'top_p': 0.85,
                'description': 'Fast text cleanup (150 tokens)'
            },
            2: {
                'model': 'deepseek-chat',
                'max_tokens': 250,
                'temperature': 0.3,
                'top_p': 0.9,
                'description': 'Standard cleanup (250 tokens)'
            },
            3: {
                'model': 'deepseek-chat',
                'max_tokens': 400,
                'temperature': 0.4,
                'top_p': 0.93,
                'description': 'Balanced cleanup (400 tokens) [DEFAULT]'
            },
            4: {
                'model': 'deepseek-chat',
                'max_tokens': 600,
                'temperature': 0.5,
                'top_p': 0.95,
                'description': 'Thorough cleanup (600 tokens)'
            },
            5: {
                'model': 'deepseek-chat',
                'max_tokens': 800,
                'temperature': 0.6,
                'top_p': 0.97,
                'description': 'Deep cleanup (800 tokens) [BEST QUALITY]'
            },
        }
    else:
        # Default profile
        profiles = {
            1: {'model': 'deepseek-chat', 'max_tokens': 200, 'temperature': 0.5},
            2: {'model': 'deepseek-chat', 'max_tokens': 300, 'temperature': 0.6},
            3: {'model': 'deepseek-chat', 'max_tokens': 400, 'temperature': 0.7},
            4: {'model': 'deepseek-chat', 'max_tokens': 600, 'temperature': 0.7},
            5: {'model': 'deepseek-chat', 'max_tokens': 800, 'temperature': 0.8},
        }
    
    return profiles.get(level, profiles[3])  # Default to level 3 if unknown
