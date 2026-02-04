import sqlite3
import sys

try:
    db = sqlite3.connect('news.db')
    c = db.cursor()
    
    # Check tables
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = c.fetchall()
    print(f"[INFO] Tables: {[t[0] for t in tables]}")
    
    # Clear bot locks
    c.execute("DELETE FROM bot_locks")
    db.commit()
    print("[OK] Bot locks cleared")
    
    db.close()
except Exception as e:
    print(f"[ERROR] {e}")
    sys.exit(1)
