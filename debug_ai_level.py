#!/usr/bin/env python3
"""Debug script to check AI levels in database"""

import sqlite3

# Open the database
db_path = "news.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check feature_flags table
print("=" * 60)
print("Feature flags in database:")
print("=" * 60)
cursor.execute("SELECT user_id, key, value FROM feature_flags WHERE key LIKE 'ai_%_level' ORDER BY user_id, key")
rows = cursor.fetchall()
for row in rows:
    print(f"  {row[0]:20s} {row[1]:20s} = {row[2]}")

if not rows:
    print("  (no AI level flags found)")

# Check if 'global' user has cleanup level set
print("\n" + "=" * 60)
print("Checking 'global' user cleanup level specifically:")
print("=" * 60)
cursor.execute("SELECT value FROM feature_flags WHERE user_id = 'global' AND key = 'ai_cleanup_level'")
result = cursor.fetchone()
if result:
    print(f"  ai_cleanup_level for 'global' = {result[0]}")
else:
    print("  ai_cleanup_level for 'global' = NOT SET (will use default)")

conn.close()
