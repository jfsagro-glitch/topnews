#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import feedparser
import requests
import sys

# Ensure UTF-8 output
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

url = 'https://ria.ru/export/rss2/archive/index.xml'

print("[1] Fetching RIA RSS...")
try:
    response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
    print(f"    Response encoding: {response.encoding}")
    print(f"    Content-Type header: {response.headers.get('content-type', 'N/A')}")
    print()
    
    # Check raw content encoding
    print("[2] Raw content check:")
    print(f"    First 200 bytes (hex): {response.content[:200]}")
    print()
    
except Exception as e:
    print(f"ERROR fetching: {e}")
    sys.exit(1)

print("[3] Parsing with feedparser...")
feed = feedparser.parse(url)
print(f"    Feed encoding: {feed.encoding}")
print(f"    Feed version: {feed.version}")
print(f"    Entries count: {len(feed.entries)}")
print()

print("[4] First 3 items (raw):")
for i, entry in enumerate(feed.entries[:3]):
    print(f"\n    [{i+1}] TITLE:")
    title = entry.get("title", "NO TITLE")
    print(f"        {repr(title)}")
    print(f"        {title}")
    
    print(f"    SUMMARY len: {len(entry.get('summary', ''))}")
    if entry.get('summary'):
        summary = entry.get('summary', '')[:100]
        print(f"        {repr(summary)}")
    
    print(f"    DESCRIPTION len: {len(entry.get('description', ''))}")
    if entry.get('description'):
        desc = entry.get('description', '')[:100]
        print(f"        {repr(desc)}")

print("\n[5] Checking for duplicates in titles:")
titles = [e.get('title', '') for e in feed.entries[:10]]
unique_titles = set(titles)
print(f"    Total items: {len(titles)}")
print(f"    Unique titles: {len(unique_titles)}")

if len(titles) != len(unique_titles):
    print("\n    DUPLICATES FOUND:")
    for title in titles:
        if titles.count(title) > 1:
            print(f"      - Count {titles.count(title)}: {title[:50]}...")
