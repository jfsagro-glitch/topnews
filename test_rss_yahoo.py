"""Test RSS parser with Yahoo feed"""
import asyncio
import sys
sys.path.insert(0, '.')

from parsers.rss_parser import RSSParser

async def test_yahoo():
    parser = RSSParser(timeout=10)
    url = 'https://news.yahoo.com/rss/world'
    source_name = 'news.yahoo.com'
    
    print(f'Testing Yahoo RSS: {url}')
    print(f'Source name: {source_name}\n')
    
    items = await parser.parse(url, source_name, max_items=5)
    
    print(f'Collected {len(items)} items\n')
    
    if items:
        for i, item in enumerate(items[:3], 1):
            print(f'{i}. {item["title"][:70]}')
            print(f'   URL: {item["url"][:60]}...')
            print(f'   Text: {item["text"][:80]}...')
            print(f'   Text length: {len(item["text"])} chars\n')
    else:
        print('No items collected!')

if __name__ == '__main__':
    asyncio.run(test_yahoo())
