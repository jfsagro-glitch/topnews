"""
Test to analyze current optimization level and quality metrics
"""
import asyncio
import sys
sys.path.insert(0, '.')

from config.config import (
    DEEPSEEK_API_ENDPOINT, DEEPSEEK_API_KEY, 
    DEEPSEEK_INPUT_COST_PER_1K_TOKENS_USD,
    DEEPSEEK_OUTPUT_COST_PER_1K_TOKENS_USD,
    AI_CATEGORY_VERIFICATION_ENABLED
)
from net.deepseek_client import DeepSeekClient
from db.database import NewsDatabase

async def test_optimization_level():
    """Test current optimization level and cost breakdown"""
    print("[TEST] Analyzing Current Optimization Level")
    print("=" * 60)
    
    # Check what's enabled/disabled
    print(f"\n1. AI SETTINGS:")
    print(f"   AI_CATEGORY_VERIFICATION_ENABLED: {AI_CATEGORY_VERIFICATION_ENABLED}")
    
    # Initialize components
    db = NewsDatabase()
    client = DeepSeekClient(db=db)
    
    # Test sample news
    sample_title = "Новые правила в Москве"
    sample_text = """В Москве вступили в силу новые правила парковки. 
    Согласно пресс-релизу, жители столицы должны будут переоформить свои разрешения."""
    
    print(f"\n2. TEST SUMMARIZATION:")
    print(f"   Title: {sample_title[:50]}...")
    print(f"   Text: {sample_text[:50]}...")
    
    # Test summarize (always enabled)
    print(f"\n   Testing summarize()...")
    summary, tokens_summary = await client.summarize(sample_title, sample_text)
    if summary:
        print(f"   ✓ Summary generated: {summary[:80]}...")
        print(f"     Tokens: {tokens_summary.get('total_tokens', 0)}")
        cost_summary = (tokens_summary['input_tokens'] / 1_000_000.0) * 0.14 + \
                      (tokens_summary['output_tokens'] / 1_000_000.0) * 0.28
        print(f"     Cost: ${cost_summary:.6f}")
    else:
        print(f"   ✗ Failed to generate summary")
    
    # Test verify_category (optional)
    if AI_CATEGORY_VERIFICATION_ENABLED:
        print(f"\n3. TEST CATEGORY VERIFICATION:")
        print(f"   Testing verify_category()...")
        category, tokens_cat = await client.verify_category(sample_title, sample_text, 'russia')
        if category:
            print(f"   ✓ Category verified: {category}")
            print(f"     Tokens: {tokens_cat.get('total_tokens', 0)}")
            cost_cat = (tokens_cat['input_tokens'] / 1_000_000.0) * 0.14 + \
                      (tokens_cat['output_tokens'] / 1_000_000.0) * 0.28
            print(f"     Cost: ${cost_cat:.6f}")
        else:
            print(f"   ✗ Failed to verify category")
    else:
        print(f"\n3. TEST CATEGORY VERIFICATION:")
        print(f"   DISABLED (AI_CATEGORY_VERIFICATION_ENABLED=False)")
    
    # Test extract_clean_text (optional)
    print(f"\n4. TEST TEXT CLEANING:")
    print(f"   Testing extract_clean_text()...")
    clean_text, tokens_clean = await client.extract_clean_text(sample_title, sample_text)
    if clean_text:
        print(f"   ✓ Text cleaned: {clean_text[:80]}...")
        print(f"     Tokens: {tokens_clean.get('total_tokens', 0)}")
        cost_clean = (tokens_clean['input_tokens'] / 1_000_000.0) * 0.14 + \
                    (tokens_clean['output_tokens'] / 1_000_000.0) * 0.28
        print(f"     Cost: ${cost_clean:.6f}")
    else:
        print(f"   ✗ Failed to clean text")
    
    # Calculate theoretical costs
    print(f"\n5. COST ANALYSIS (per 50 calls):")
    print(f"   Current setup:")
    
    # Assuming average tokens per operation
    avg_tokens_per_call = 300  # summarize
    
    # Cost scenarios
    scenario_current = (avg_tokens_per_call * 0.6 / 1_000_000.0) * 0.14 + \
                      (avg_tokens_per_call * 0.4 / 1_000_000.0) * 0.28
    
    # If we enable all features
    scenario_full = scenario_current * 3  # 3 operations
    
    print(f"   - Summarize only: ${scenario_current * 50:.4f} per 50 calls")
    print(f"   - With category + cleaning: ${scenario_full * 50:.4f} per 50 calls")
    print(f"   - Daily (600 calls): ${scenario_current * 600:.2f} (current) vs ${scenario_full * 600:.2f} (full)")
    
    print(f"\n6. RECOMMENDATION:")
    if AI_CATEGORY_VERIFICATION_ENABLED:
        print(f"   Current: Mixed mode (some features on)")
        print(f"   Suggestion: Verify what's actually being used vs skipped")
    else:
        print(f"   Current: Minimal mode (only summarize)")
        print(f"   Suggestion: Enable category verification and text cleaning for quality")
    
    print("\n" + "=" * 60)

if __name__ == '__main__':
    asyncio.run(test_optimization_level())
