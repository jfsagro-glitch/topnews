"""
Скрипт для сброса состояний источников в базе данных.
Устанавливает next_fetch_at=0 для всех источников, чтобы они немедленно собирались.
"""
import sqlite3
import time
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'news.db')

def reset_source_fetch_states():
    """Reset all source fetch states to allow immediate collection."""
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check current states
    cursor.execute("SELECT COUNT(*) FROM source_fetch_state")
    total = cursor.fetchone()[0]
    print(f"Total sources in source_fetch_state: {total}")
    
    cursor.execute("""
        SELECT url, source_name, next_fetch_at, last_status, error_streak
        FROM source_fetch_state
        WHERE next_fetch_at > ?
    """, (time.time(),))
    
    blocked_sources = cursor.fetchall()
    if blocked_sources:
        print(f"\nBlocked sources (next_fetch_at in future): {len(blocked_sources)}")
        for url, name, next_fetch, status, streak in blocked_sources[:10]:
            next_in = int((next_fetch - time.time()) / 60)
            print(f"  - {name}: next in {next_in} min, status={status}, errors={streak}")
        if len(blocked_sources) > 10:
            print(f"  ... and {len(blocked_sources) - 10} more")
    
    # Reset all sources to allow immediate fetch
    cursor.execute("""
        UPDATE source_fetch_state
        SET next_fetch_at = 0,
            error_streak = 0,
            last_status = 'RESET',
            last_error_code = NULL
    """)
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    print(f"\n✓ Reset {affected} sources to allow immediate collection")
    print("Sources can now be collected on next cycle")

if __name__ == "__main__":
    reset_source_fetch_states()
