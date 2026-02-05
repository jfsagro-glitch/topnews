#!/usr/bin/env python3
"""Check source names in the database"""

import sqlite3

db_path = "db/news_sandbox.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=" * 60)
print("Sources that contain 'lenta' or 'ria':")
print("=" * 60)
cursor.execute("SELECT DISTINCT source FROM sources WHERE LOWER(source) LIKE '%lenta%' OR LOWER(source) LIKE '%ria%' ORDER BY source")
sources = cursor.fetchall()
for (source,) in sources:
    print(f"  '{source}'")

if not sources:
    print("  (none found)")

print("\n" + "=" * 60)
print("All sources in database:")
print("=" * 60)
cursor.execute("SELECT DISTINCT source FROM sources ORDER BY source")
sources = cursor.fetchall()
for (source,) in sources:
    print(f"  '{source}'")

conn.close()
