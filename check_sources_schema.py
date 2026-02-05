#!/usr/bin/env python3
"""Check sources table schema"""

import sqlite3

db_path = "db/news_sandbox.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=" * 60)
print("Sources table schema:")
print("=" * 60)
cursor.execute("PRAGMA table_info(sources)")
columns = cursor.fetchall()
for col in columns:
    print(f"  {col}")

print("\n" + "=" * 60)
print("First few rows of sources:")
print("=" * 60)
cursor.execute("SELECT * FROM sources LIMIT 3")
rows = cursor.fetchall()
for row in rows:
    print(f"  {row}")

conn.close()
