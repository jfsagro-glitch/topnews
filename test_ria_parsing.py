"""
Test RIA.ru RSS parsing to debug duplicates and missing content
"""
import asyncio
import sys
sys.path.insert(0, '.')

from parsers.rss_parser import RSSParser
from db.database import NewsDatabase

async def test_ria_parsing():
    """Test RIA.ru RSS feed parsing"""
    
    print("=" * 70)
    print("RIA.ru RSS PARSING TEST")
    print("=" * 70)
    
    db = NewsDatabase()
    parser = RSSParser(db=db)
    
    # RIA RSS URL
    ria_url = "https://ria.ru/export/rss2/archive/index.xml"
    
    print(f"\n[1] Fetching RSS from: {ria_url}\n")
    
    news_items = await parser.parse(ria_url, "ria.ru")
    
    print(f"[2] Parsed {len(news_items)} items\n")
    
    if news_items:
        # Show first 5 items
        for i, item in enumerate(news_items[:5], 1):
            print(f"\n[Item {i}]")
            print(f"  Title: {item.get('title', 'N/A')[:80]}")
            print(f"  URL: {item.get('url', 'N/A')[:60]}")
            print(f"  Text length: {len(item.get('text', ''))}")
            if item.get('text'):
                print(f"  Text preview: {item.get('text', '')[:100]}...")
            else:
                print(f"  Text: EMPTY or SHORT")
            print(f"  Source: {item.get('source', 'N/A')}")
    
    # Check for duplicates
    print(f"\n[3] DUPLICATE CHECK:")
    titles = [item.get('title', '') for item in news_items]
    
    # Count unique titles
    unique_titles = set(titles)
    print(f"  Total items: {len(titles)}")
    print(f"  Unique titles: {len(unique_titles)}")
    
    if len(titles) > len(unique_titles):
        print(f"  Duplicates found: {len(titles) - len(unique_titles)}")
        
        # Find and show duplicates
        from collections import Counter
        counts = Counter(titles)
        duplicates = {t: c for t, c in counts.items() if c > 1}
        for title, count in duplicates.items():
            print(f"    - '{title[:60]}' appears {count} times")
    
    print(f"\n[4] CONTENT ANALYSIS:")
    
    items_with_text = sum(1 for item in news_items if item.get('text') and len(item.get('text', '')) > 40)
    items_without_text = sum(1 for item in news_items if not item.get('text') or len(item.get('text', '')) <= 40)
    
    print(f"  Items with full text (>40 chars): {items_with_text}")
    print(f"  Items without full text: {items_without_text}")
    
    # Average text length
    text_lengths = [len(item.get('text', '')) for item in news_items]
    if text_lengths:
        avg_length = sum(text_lengths) / len(text_lengths)
        print(f"  Average text length: {int(avg_length)} chars")
    
    print("\n" + "=" * 70)

if __name__ == '__main__':
    asyncio.run(test_ria_parsing())
