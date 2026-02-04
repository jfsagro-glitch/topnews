#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import json

conn = sqlite3.connect('db/news.db')
cursor = conn.cursor()

print('[1] rss_cache schema:')
cursor.execute('PRAGMA table_info(rss_cache)')
for col in cursor.fetchall():
    print(f'    {col[1]:20} {col[2]}')

cursor.execute('SELECT COUNT(*) FROM rss_cache')
count = cursor.fetchone()[0]
print(f'\nTotal cached RSS sources: {count}')

if count > 0:
    print('\n[2] Cached RSS sources:')
    cursor.execute('SELECT url, cached_at FROM rss_cache ORDER BY cached_at DESC')
    
    for url, cached_at in cursor.fetchall():
        print(f'\n    URL: {url}')
        print(f'    Cached: {cached_at}')

# Check ai_summaries for duplicates
print('\n[3] AI Summaries (processed articles):')
cursor.execute('SELECT COUNT(*) FROM ai_summaries')
count = cursor.fetchone()[0]
print(f'Total summaries: {count}')

if count > 0:
    cursor.execute('''
    SELECT url, title, category, created_at
    FROM ai_summaries
    WHERE source = 'ria.ru'
    ORDER BY created_at DESC
    LIMIT 10
    ''')
    
    try:
        items = cursor.fetchall()
        print(f'RIA.ru summaries: {len(items)}')
        for title, category, created_at in items:
            print(f'  {title[:50]}... [{category}]')
    except:
        # Try without source filter
        cursor.execute('''
        SELECT title, category, created_at
        FROM ai_summaries
        ORDER BY created_at DESC
        LIMIT 10
        ''')
        items = cursor.fetchall()
        print(f'Total summaries in limit: {len(items)}')
        for title, category, created_at in items:
            print(f'  {title[:50]}... [{category}]')

conn.close()
