"""Test Yahoo RSS feed access and structure"""
import feedparser
import requests
import sys

url = 'https://news.yahoo.com/rss/world'
print(f'Fetching: {url}', flush=True)

try:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    }
    r = requests.get(url, timeout=8, headers=headers)
    print(f'Status: {r.status_code}\n', flush=True)
    
    if r.status_code == 200:
        # Show raw XML snippet
        print('Raw XML (first 2000 chars):', flush=True)
        print(r.text[:2000], flush=True)
        print('\n' + '='*50 + '\n', flush=True)
        
        feed = feedparser.parse(r.text)
        print(f'Feed entries: {len(feed.entries)}\n', flush=True)
        
        if feed.entries:
            entry = feed.entries[0]
            print(f'First entry title: {entry.title}\n', flush=True)
            print('Entry keys:', list(entry.keys()), flush=True)
        else:
            print('No entries in feed', flush=True)
    else:
        print(f'HTTP error: {r.status_code}', flush=True)
        
except requests.Timeout:
    print('Error: Request timeout', flush=True)
except Exception as e:
    print(f'Error: {type(e).__name__}: {e}', flush=True)
    sys.exit(1)
