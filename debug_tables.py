#!/usr/bin/env python3
"""Debug script to check database structure"""

import sqlite3

# Open the database
db_path = "news.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# List all tables
print("=" * 60)
print("Tables in database:")
print("=" * 60)
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()
for (table_name,) in tables:
    print(f"  {table_name}")
    # Count rows
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    print(f"    -> {count} rows")

conn.close()
