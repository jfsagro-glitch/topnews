# Configuration Reference

## AI budget and gating

- `AI_DAILY_BUDGET_USD` (default: 4.0)
  - Daily budget in USD for AI calls.
- `AI_DAILY_MIN_RESERVE_USD` (default: 0.25)
  - Reserve to avoid hard cutoffs on small cost jitter.
- `AI_DAILY_BUDGET_TOKENS` (default: 0)
  - Token fallback when USD cost is unavailable (0 disables).
- `AI_CALLS_PER_TICK_MAX` (default: 6)
  - Maximum AI calls allowed per tick.

## AI input limits

- `AI_MAX_INPUT_CHARS` (default: 3200)
  - Max input size for summary and cleanup.
- `AI_MAX_INPUT_CHARS_HASHTAGS` (default: 1800)
  - Max input size for hashtag tasks.
- `SUMMARY_MIN_CHARS` (default: 900)
  - Minimum cleaned length for summary calls.
- `AI_SUMMARY_MIN_CHARS` (default: `SUMMARY_MIN_CHARS`)
  - Override for summary minimum length.
