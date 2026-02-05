#!/usr/bin/env python3
"""Debug script to set AI level to 5"""

import sqlite3

# Open the database
db_path = "db/news_sandbox.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Set cleanup level to 5 for global user
cursor.execute('''
    INSERT OR REPLACE INTO feature_flags (user_id, key, value, updated_at) 
    VALUES ('global', 'ai_cleanup_level', '5', CURRENT_TIMESTAMP)
''')
conn.commit()

print("Set ai_cleanup_level for 'global' to 5")

# Verify
cursor.execute("SELECT value FROM feature_flags WHERE user_id = 'global' AND key = 'ai_cleanup_level'")
result = cursor.fetchone()
print(f"Verified: ai_cleanup_level = {result[0] if result else 'NOT SET'}")

conn.close()
