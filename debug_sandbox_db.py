#!/usr/bin/env python3
"""Debug script to check sandbox database structure"""

import sqlite3

# Open the database
db_path = "db/news_sandbox.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# List all tables
print("=" * 60)
print("Tables in sandbox database:")
print("=" * 60)
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()
for (table_name,) in tables:
    print(f"  {table_name}")
    # Count rows
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    print(f"    -> {count} rows")

print("\n" + "=" * 60)
print("Feature flags (AI levels):")
print("=" * 60)
cursor.execute("SELECT user_id, key, value FROM feature_flags ORDER BY user_id, key")
rows = cursor.fetchall()
for row in rows:
    print(f"  {row[0]:20s} {row[1]:25s} = {row[2]}")

if not rows:
    print("  (no feature flags)")

conn.close()
