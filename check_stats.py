"""Check AI usage statistics in database"""
import sqlite3
import os

db_path = 'db/news.db'

if not os.path.exists(db_path):
    print(f"❌ Database not found: {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check if ai_usage table exists
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ai_usage'")
if not cursor.fetchone():
    print("❌ Table ai_usage does not exist")
    exit(1)

# Get AI usage stats
cursor.execute("""
    SELECT 
        total_requests, 
        total_tokens, 
        total_cost_usd,
        summarize_requests,
        summarize_tokens,
        category_requests,
        category_tokens,
        text_clean_requests,
        text_clean_tokens,
        updated_at
    FROM ai_usage 
    WHERE id = 1
""")

row = cursor.fetchone()
if not row:
    print("❌ No AI usage data found")
    exit(1)

print("=" * 60)
print("🧠 AI USAGE STATISTICS")
print("=" * 60)
print(f"\n📊 TOTAL:")
print(f"  Requests:  {row[0]:,}")
print(f"  Tokens:    {row[1]:,}")
print(f"  Cost:      ${row[2]:.4f}")

print(f"\n📝 SUMMARIZE (пересказы):")
print(f"  Requests:  {row[3]:,}")
print(f"  Tokens:    {row[4]:,}")

print(f"\n🏷️ CATEGORY (верификация категорий):")
print(f"  Requests:  {row[5]:,}")
print(f"  Tokens:    {row[6]:,}")

print(f"\n✨ TEXT_CLEAN (очистка текста):")
print(f"  Requests:  {row[7]:,}")
print(f"  Tokens:    {row[8]:,}")

print(f"\n⏰ Last Updated: {row[9]}")
print("=" * 60)

# Compare with DeepSeek screenshot
print(f"\n🔍 COMPARISON WITH DEEPSEEK API:")
print(f"  DeepSeek total tokens: 197,947")
print(f"  Database total tokens: {row[1]:,}")
print(f"  Difference:            {197947 - row[1]:,} tokens")
print(f"  Match:                 {'✅ YES' if abs(197947 - row[1]) < 1000 else '❌ NO'}")

print(f"\n  DeepSeek cost:         $0.02")
print(f"  Database cost:         ${row[2]:.4f}")
print(f"  Difference:            ${abs(0.02 - row[2]):.4f}")

conn.close()
