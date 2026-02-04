#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3

conn = sqlite3.connect('db/news.db')
cursor = conn.cursor()

# Check published_news table
print('[1] published_news table:')
cursor.execute('SELECT COUNT(*) FROM published_news')
total = cursor.fetchone()[0]
print(f'    Total rows: {total}')

if total > 0:
    cursor.execute('SELECT title, source, published_at FROM published_news ORDER BY published_at DESC LIMIT 5')
    print('\n    Last 5 articles:')
    for title, source, pub_at in cursor.fetchall():
        print(f'      - {title[:50]}... [{source}]')
        print(f'        {pub_at}')
else:
    print('    (Empty - no articles published yet)')

# Check how many duplicates would be detected
print('\n[2] Testing deduplication logic:')
from db.database import NewsDatabase

try:
    db = NewsDatabase()
    # Test some titles from РИА
    test_titles = [
        "МИД прокомментировали отсутствие ответа США на идею России по ДСНВ",
        "В МИД России прокомментировали истечение сроков ДСНВ",
        "Россия по истечении ДСНВ будет действовать ответственно",
    ]
    
    for title in test_titles:
        is_dup = db.is_similar_title_published(title, threshold=0.75)
        print(f'\n    Title: {title[:50]}...')
        print(f'    Would be blocked: {is_dup}')
        
        # Test with different threshold
        is_dup_strict = db.is_similar_title_published(title, threshold=0.90)
        print(f'    (Threshold 0.90): {is_dup_strict}')
        
except Exception as e:
    print(f'    ERROR: {e}')

conn.close()
