#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Complete AI system diagnostic - traces entire flow from env vars to API calls.
"""
import os
import sys
import asyncio
from pathlib import Path
import logging

# Force UTF-8 encoding
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

async def main():
    print("=" * 70)
    print("AI SYSTEM DIAGNOSTIC - COMPLETE FLOW CHECK")
    print("=" * 70)
    
    # ============ STEP 1: Environment variables ============
    print("\n1️⃣  ENVIRONMENT VARIABLES:")
    api_key_env = os.getenv('DEEPSEEK_API_KEY', '')
    print(f"   DEEPSEEK_API_KEY exists: {bool(api_key_env)}")
    print(f"   DEEPSEEK_API_KEY length: {len(api_key_env)}")
    if api_key_env:
        print(f"   Key preview: {api_key_env[:10]}...{api_key_env[-5:]}")
    
    # ============ STEP 2: Config file ============
    print("\n2️⃣  CONFIG FILE LOADING:")
    api_key_file = ''
    try:
        from config.config import DEEPSEEK_API_KEY, DEEPSEEK_API_ENDPOINT, APP_ENV
        api_key_file = DEEPSEEK_API_KEY
        print(f"   ✅ config.py loaded successfully")
        print(f"   - APP_ENV: {APP_ENV}")
        print(f"   - DEEPSEEK_API_KEY from config: {bool(api_key_file)}")
        print(f"   - DEEPSEEK_API_ENDPOINT: {DEEPSEEK_API_ENDPOINT}")
        if api_key_file:
            print(f"   - Key preview: {api_key_file[:10]}...{api_key_file[-5:]}")
    except Exception as e:
        print(f"   ❌ Error loading config: {e}")
        return 1
    
    # Determine which key will be used
    effective_key = api_key_env or api_key_file
    print(f"\n   Effective key (env OR config): {bool(effective_key)}")
    if not effective_key:
        print("\n❌ CRITICAL: No API key found in environment or config!")
        return 1
    
    # Check app environment
    app_env = os.getenv('APP_ENV', 'unknown')
    print(f"\n2. APP ENVIRONMENT: {app_env}")
    
    # ============ STEP 3: Database ============
    print("\n3️⃣  DATABASE INITIALIZATION:")
    try:
        try:
            from config.railway_config import DATABASE_PATH, ACCESS_DB_PATH
        except (ImportError, ValueError):
            from config.config import DATABASE_PATH, ACCESS_DB_PATH
        
        from db.database import NewsDatabase
        db = NewsDatabase()
        print(f"   ✅ Main DB connected")
        
        from core.services.access_control import AILevelManager
        ai_manager = AILevelManager(db)
        summary_level = ai_manager.get_level('global', 'summary')
        print(f"   ✅ AI Summary Level: {summary_level}")
        if summary_level == 0 and APP_ENV == 'sandbox':
            print("      ⚠️  Level is 0 (disabled in sandbox mode)")
    except Exception as e:
        print(f"   ❌ Database error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # ============ STEP 4: Global stop check ============
    print("\n4️⃣  GLOBAL STOP & COLLECTION STATUS:")
    try:
        from core.services.global_stop import get_global_stop_state
        state = get_global_stop_state()
        print(f"   - Global stop enabled: {state.enabled}")
        if state.enabled:
            print("      ⚠️  WARNING: Global stop is ENABLED - AI calls blocked!")
            print("      Action: Use /management to resume collection")
    except Exception as e:
        print(f"   ⚠️  Error checking global stop: {e}")
    
    # ============ STEP 5: DeepSeekClient initialization ============
    print("\n5️⃣  DEEPSEEK CLIENT INITIALIZATION:")
    try:
        from net.deepseek_client import DeepSeekClient
        
        # Initialize without explicit key - should get it from env
        client = DeepSeekClient(db=db)
        print(f"   ✅ DeepSeekClient initialized")
        print(f"      - Client.api_key (instance): {bool(client.api_key)}")
        print(f"      - Has budget manager: {bool(client.budget)}")
        print(f"      - Has cache manager: {bool(client.cache)}")
        print(f"      - Circuit breaker open: {client._circuit_open()}")
        
        if client.budget:
            state = client.budget.get_state()
            print(f"      - Daily cost so far: ${state.get('daily_cost', 0):.4f}")
            budget_ok = state.get('budget_ok', 'unknown')
            print(f"      - Budget status: {'✅ OK' if budget_ok else '❌ EXCEEDED'}")
        
        if client.cache:
            stats = client.cache.get_stats()
            print(f"      - Cache hits: {stats.get('hits', 0)}")
            print(f"      - Cache misses: {stats.get('misses', 0)}")
            
    except Exception as e:
        print(f"   ❌ DeepSeekClient initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # ============ STEP 6: Test API call ============
    print("\n6️⃣  TEST API CALL (summarize):")
    try:
        test_text = """
        Russia's economy is growing faster than expected in Q3 2026. 
        The central bank reports strong performance with GDP growth at 3.2%.
        Inflation remains under control at 4.5% annually.
        """
        test_title = "Russia Economy Shows Strong Growth"
        
        print(f"   Calling DeepSeek API with allow_short=True...")
        summary, token_usage = await client.summarize(
            title=test_title,
            text=test_text,
            level=3,
            allow_short=True
        )
        
        if summary:
            print(f"   ✅ API CALL SUCCESSFUL!")
            print(f"      Summary: {summary[:80]}...")
            print(f"      Tokens used: {token_usage.get('total_tokens', 0)}")
            print(f"      Cache hit: {token_usage.get('cache_hit', False)}")
            print(f"      Cost: ${token_usage.get('cost_usd', 0):.6f}")
        else:
            print(f"   ❌ API returned None (no summary)")
            print(f"      Token usage dict: {token_usage}")
            if 'budget_exceeded' in token_usage and token_usage['budget_exceeded']:
                print("      Reason: Daily budget exceeded")
            elif 'circuit_open' in token_usage and token_usage['circuit_open']:
                print("      Reason: Circuit breaker is open (too many failures)")
            elif 'disabled' in token_usage and token_usage['disabled']:
                print("      Reason: AI Summary level is 0 (disabled)")
            else:
                print("      Reason: Unknown (check API error)")
    except Exception as e:
        print(f"   ❌ API CALL FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # ============ Summary ============
    print("\n" + "=" * 70)
    if summary:
        print("✅ ALL CHECKS PASSED - AI System is working correctly!")
    else:
        print("⚠️  Setup complete but API call returned no summary")
        print("   Check the token_usage dict above for error details")
    print("=" * 70)
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
