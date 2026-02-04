#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3

conn = sqlite3.connect('db/news.db')
cursor = conn.cursor()

print('[1] rss_cache schema:')
cursor.execute('PRAGMA table_info(rss_cache)')
for col in cursor.fetchall():
    print(f'    {col[1]:20} {col[2]}')

cursor.execute('SELECT COUNT(*) FROM rss_cache')
count = cursor.fetchone()[0]
print(f'\nTotal cached RSS items: {count}')

if count > 0:
    print('\n[2] Recent RIA items in cache (last 10):')
    cursor.execute('''
    SELECT url, title, lead_text, source, cached_at
    FROM rss_cache
    WHERE source = 'ria.ru'
    ORDER BY cached_at DESC
    LIMIT 10
    ''')
    
    items = cursor.fetchall()
    print(f'RIA.ru items in cache: {len(items)}')
    for i, (url, title, lead, source, cached) in enumerate(items, 1):
        print(f'\n[{i}] {title[:50]}...')
        print(f'    URL: {url[:60]}...')
        print(f'    Lead len: {len(lead) if lead else 0}')
        if lead:
            print(f'    Lead: {lead[:60]}...')

conn.close()
