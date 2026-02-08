#!/usr/bin/env python3
"""Check source names in the database"""

import sqlite3
import os

db_path = "db/news_sandbox.db"
if not os.path.exists(db_path):
    db_path = "db/news.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=" * 60)
print("Sources that contain 'lenta' or 'ria':")
print("=" * 60)
cursor.execute(
    "SELECT DISTINCT code, title FROM sources "
    "WHERE LOWER(code) LIKE '%lenta%' OR LOWER(code) LIKE '%ria%' "
    "OR LOWER(title) LIKE '%lenta%' OR LOWER(title) LIKE '%ria%' "
    "ORDER BY code"
)
sources = cursor.fetchall()
for code, title in sources:
    print(f"  '{code}' - {title}")

if not sources:
    print("  (none found)")

print("\n" + "=" * 60)
print("All sources in database:")
print("=" * 60)
cursor.execute("SELECT DISTINCT code, title FROM sources ORDER BY code")
sources = cursor.fetchall()
for code, title in sources:
    print(f"  '{code}' - {title}")

conn.close()
