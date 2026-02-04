#!/usr/bin/env python3
"""
Wrapper to run bot.py with Windows console buffer fix
"""
import sys
import os
import sqlite3
import warnings

# Suppress warnings
warnings.filterwarnings('ignore')

# Set environment variables for compatibility
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
os.environ['PYTHONLEGACYWINDOWSSTDIO'] = '0'

# Reset bot lock in database if it exists
try:
    from config.config import DATABASE_PATH
    db_path = DATABASE_PATH
except:
    db_path = 'news.db'

if os.path.exists(db_path):
    try:
        db = sqlite3.connect(db_path, timeout=5)
        c = db.cursor()
        # Check if bot_lock table exists and clear ALL locks (aggressive mode)
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bot_lock'")
        if c.fetchone():
            import time
            now = int(time.time())
            # Delete ALL locks regardless of age (safety for restart)
            c.execute("DELETE FROM bot_lock")
            db.commit()
            print("[INFO] All bot locks cleared from database (restart mode)")
        db.close()
    except Exception as e:
        print(f"[WARNING] Could not clear locks: {e}")
        # If DB is locked/broken, delete it and let bot recreate
        try:
            if os.path.exists(db_path):
                os.remove(db_path)
                print(f"[INFO] Removed corrupted database: {db_path}")
        except:
            pass

# Remove handlers before importing anything
logging_config_file = os.path.join(os.path.dirname(__file__), 'utils', 'logger.py')
if os.path.exists(logging_config_file):
    print("[INFO] Found logger.py - using patched version")

# Now run bot
if __name__ == '__main__':
    try:
        print("[INFO] Starting News Bot...")
        print("=" * 50)
        
        # Import and run
        from bot import NewsBot
        import asyncio
        
        async def main():
            bot = NewsBot()
            await bot.start()
        
        # Run with asyncio
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[STOP] Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
