#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import sys
import io

# Ensure UTF-8 output
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, '.')

async def test_ria_fetch():
    from net.http_client import get_http_client
    from utils.lead_extractor import extract_lead_from_html
    import feedparser
    
    # Get RIA RSS
    print("[1] Fetching RIA RSS feed...")
    feed = feedparser.parse('https://ria.ru/export/rss2/archive/index.xml')
    print(f"    Found {len(feed.entries)} items")
    
    # Test first 3 articles
    print("\n[2] Testing article fetch for first 3 items:")
    http_client = await get_http_client()
    
    for i, entry in enumerate(feed.entries[:3], 1):
        title = entry.get('title', 'No title')
        url = entry.get('link', '')
        
        print(f"\n    [{i}] {title[:60]}...")
        print(f"        URL: {url}")
        
        if not url:
            print(f"        ERROR: No URL found")
            continue
        
        try:
            print(f"        Fetching article...")
            response = await http_client.get(url, retries=1)
            html = response.text
            
            # Try to extract lead
            lead = extract_lead_from_html(html, max_len=200)
            if lead:
                print(f"        ✅ Lead extracted ({len(lead)} chars):")
                print(f"           {lead[:100]}...")
            else:
                print(f"        ⚠️  No lead extracted from HTML")
                print(f"           HTML size: {len(html)} bytes")
                
        except Exception as e:
            print(f"        ❌ Error: {e}")

if __name__ == '__main__':
    asyncio.run(test_ria_fetch())
