#!/usr/bin/env python3
"""Comprehensive test to trace auto-summarization flow"""

import sys
import os

# Add the current directory to the path
sys.path.insert(0, os.getcwd())

from db.database import NewsDatabase
from core.services.access_control import AILevelManager

# Use sandbox database
db = NewsDatabase(db_path='db/news_sandbox.db')

# Initialize AI manager
ai_manager = AILevelManager(db)

print("=" * 60)
print("Step 1: Check current cleanup level for 'global'")
print("=" * 60)
current_level = ai_manager.get_level('global', 'cleanup')
print(f"Current cleanup level: {current_level}")

print("\n" + "=" * 60)
print("Step 2: Simulate clicking + button (increment)")
print("=" * 60)
new_level = ai_manager.inc_level('global', 'cleanup')
print(f"New cleanup level: {new_level}")

print("\n" + "=" * 60)
print("Step 3: Verify in database")
print("=" * 60)
verify_level = ai_manager.get_level('global', 'cleanup')
print(f"Verified cleanup level: {verify_level}")

print("\n" + "=" * 60)
print("Step 4: Test the auto-summarize condition")
print("=" * 60)
cleanup_level = verify_level
source = "lenta.ru"
should_auto_summarize = cleanup_level == 5 and ('lenta.ru' in source or 'ria.ru' in source)
print(f"cleanup_level = {cleanup_level}")
print(f"source = '{source}'")
print(f"Should auto-summarize: {should_auto_summarize}")

if should_auto_summarize:
    print("✅ Auto-summarization WOULD BE TRIGGERED")
else:
    print("❌ Auto-summarization WOULD NOT BE TRIGGERED")
    print(f"   Reason: cleanup_level ({cleanup_level}) != 5")

db.close()
