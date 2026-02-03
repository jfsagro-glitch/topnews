#!/usr/bin/env python3
"""
Test script to debug DeepSeek API issues
"""
import os
import asyncio
import httpx

async def test_deepseek():
    api_key = os.getenv('DEEPSEEK_API_KEY', '').strip()
    
    print(f"✓ API Key status:")
    print(f"  - Exists: {bool(api_key)}")
    print(f"  - Length: {len(api_key)}")
    if api_key:
        print(f"  - Starts with: {api_key[:20]}...")
    
    if not api_key:
        print("\n❌ ERROR: DEEPSEEK_API_KEY is not set!")
        print("   Set it with: export DEEPSEEK_API_KEY='your-key-here'")
        return
    
    endpoint = 'https://api.deepseek.com/v1/chat/completions'
    
    payload = {
        "model": "deepseek-v3",
        "messages": [
            {"role": "system", "content": "Ты помощник."},
            {"role": "user", "content": "Привет!"},
        ],
        "temperature": 0.7,
        "max_tokens": 100,
    }
    
    print(f"\n✓ Testing API endpoint: {endpoint}")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
        
        print(f"✓ Response status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ API is working!")
            data = response.json()
            print(f"   Response: {data['choices'][0]['message']['content'][:100]}")
        else:
            print(f"❌ API Error: {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            
    except Exception as e:
        print(f"❌ Connection error: {e}")

if __name__ == "__main__":
    asyncio.run(test_deepseek())
