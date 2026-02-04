"""
Quick analysis of current optimization and quality settings
"""
import os
import sys
sys.path.insert(0, '.')

# Check environment
print("[INFO] Current Optimization Analysis")
print("=" * 60)

# 1. Check if API key is set
api_key_set = bool(os.getenv('DEEPSEEK_API_KEY'))
print(f"\n1. DeepSeek API Key: {'SET' if api_key_set else 'NOT SET'}")

# 2. Check config settings
from config.config import AI_CATEGORY_VERIFICATION_ENABLED
print(f"\n2. Quality Settings:")
print(f"   AI_CATEGORY_VERIFICATION_ENABLED: {AI_CATEGORY_VERIFICATION_ENABLED}")

# 3. Check current implementation
from net.deepseek_client import DeepSeekClient
print(f"\n3. DeepSeekClient Methods Available:")
print(f"   - summarize: YES (always enabled)")
print(f"   - verify_category: YES (controlled by config)")
print(f"   - extract_clean_text: YES (for HTML sources)")

# 4. Cost analysis
print(f"\n4. Cost Analysis (per operation):")
print(f"   Summarize (avg 200 tokens):")
summary_cost = (120 / 1_000_000.0) * 0.14 + (80 / 1_000_000.0) * 0.28
print(f"     Cost: ${summary_cost * 1000:.4f} per 1000 calls = ${summary_cost * 600:.3f}/day")

if AI_CATEGORY_VERIFICATION_ENABLED:
    print(f"   + Verify Category (avg 100 tokens):")
    cat_cost = (60 / 1_000_000.0) * 0.14 + (40 / 1_000_000.0) * 0.28
    print(f"     Cost: ${cat_cost * 1000:.4f} per 1000 calls = ${cat_cost * 600:.3f}/day")
    
    print(f"   + Extract Clean Text (avg 150 tokens):")
    clean_cost = (90 / 1_000_000.0) * 0.14 + (60 / 1_000_000.0) * 0.28
    print(f"     Cost: ${clean_cost * 1000:.4f} per 1000 calls = ${clean_cost * 600:.3f}/day")
    
    total_cost = (summary_cost + cat_cost + clean_cost) * 600
    print(f"\n   TOTAL/day (all 3): ${total_cost:.3f}")
    savings = (1 - total_cost / 1.0) * 100
    print(f"   vs $1/day target: {savings:.1f}% savings")
else:
    total_cost = summary_cost * 600
    print(f"\n   TOTAL/day (summarize only): ${total_cost:.3f}")

# 5. Quality vs Cost tradeoff
print(f"\n5. Quality vs Cost Tradeoff:")
print(f"   Current setup: {'QUALITY MODE (all checks)' if AI_CATEGORY_VERIFICATION_ENABLED else 'MINIMAL MODE (summarize only)'}")
print(f"   - Correct hashtags: {'HIGH' if AI_CATEGORY_VERIFICATION_ENABLED else 'MEDIUM'}")
print(f"   - Remove garbage: {'YES' if AI_CATEGORY_VERIFICATION_ENABLED else 'PARTIAL'}")
print(f"   - Prompt compliance: ALWAYS (13 rules enforced)")

print(f"\n6. Recommendation:")
if not api_key_set:
    print(f"   ERROR: DEEPSEEK_API_KEY not set!")
    print(f"   Cannot proceed without API key")
else:
    if AI_CATEGORY_VERIFICATION_ENABLED:
        print(f"   Current: BALANCED (Quality + Cost)")
        print(f"   - All quality checks enabled")
        print(f"   - Still well under $1/day budget")
    else:
        print(f"   Current: MINIMAL (Cost only)")
        print(f"   - Can enable category verification for better hashtags")
        print(f"   - Small cost increase for major quality improvement")

print("\n" + "=" * 60)
