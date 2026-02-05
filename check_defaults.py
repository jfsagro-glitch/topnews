#!/usr/bin/env python3
"""Test summary level defaults"""

import sys
import os
sys.path.insert(0, os.getcwd())

from db.database import NewsDatabase
from core.services.access_control import AILevelManager

db = NewsDatabase(db_path='db/news_sandbox.db')
ai_manager = AILevelManager(db)

print("Current summary level for 'global':", ai_manager.get_level('global', 'summary'))
print("Current cleanup level for 'global':", ai_manager.get_level('global', 'cleanup'))

# Check defaults from environment/code
from core.services.access_control import AI_SUMMARY_LEVEL_DEFAULT, AI_CLEANUP_LEVEL_DEFAULT
print(f"\nDefault summary level: {AI_SUMMARY_LEVEL_DEFAULT}")
print(f"Default cleanup level: {AI_CLEANUP_LEVEL_DEFAULT}")
