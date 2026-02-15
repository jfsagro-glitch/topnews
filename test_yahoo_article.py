"""Test fetching article content from Yahoo"""
import requests
from utils.lead_extractor import extract_lead_from_html

# Test URL from Yahoo RSS
url = 'https://www.yahoo.com/news/articles/zapotec-tomb-600-ce-marks-072630174.html'

print(f'Fetching: {url}\n')

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

try:
    r = requests.get(url, timeout=10, headers=headers, allow_redirects=True)
    print(f'Status: {r.status_code}')
    print(f'Final URL: {r.url}')
    print(f'Content length: {len(r.text)} bytes')
    
    if 'consent.yahoo.com' in r.url:
        print('\n⚠️ REDIRECTED TO CONSENT PAGE')
    else:
        print('\n✓ No consent redirect')
        
        # Try to extract lead
        lead = extract_lead_from_html(r.text, max_len=400)
        if lead:
            print(f'\n✓ Extracted lead ({len(lead)} chars):')
            print(lead)
        else:
            print('\n✗ Could not extract lead')
            print(f'\nHTML snippet: {r.text[:500]}')
    
except Exception as e:
    print(f'Error: {e}')
