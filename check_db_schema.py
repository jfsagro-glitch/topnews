#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3

conn = sqlite3.connect('db/news.db')
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print('[1] Database tables:')
for table in tables:
    print(f'    - {table[0]}')

# Get schema for main table
if tables:
    main_table = tables[0][0]
    print(f'\n[2] {main_table} schema:')
    cursor.execute(f'PRAGMA table_info({main_table})')
    for col in cursor.fetchall():
        print(f'    {col[1]:20} {col[2]}')
    
    # Get sample data
    print(f'\n[3] Sample data from {main_table}:')
    cursor.execute(f'SELECT COUNT(*) FROM {main_table}')
    count = cursor.fetchone()[0]
    print(f'    Total rows: {count}')
    
    cursor.execute(f'SELECT * FROM {main_table} LIMIT 1')
    row = cursor.fetchone()
    if row:
        print(f'    Columns: {[desc[0] for desc in cursor.description]}')
        print(f'    First row: {row}')

conn.close()
