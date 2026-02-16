# Railway Cost Optimization

## Summary

This document describes additional cost optimizations focused on RSSHub usage and network load.

## RSSHub Mitigation (Bot Side)

- Per-source minimum fetch interval:
  - RSSHub (Telegram/X): default 900s (15m)
  - RSS/HTML: default 300s (5m)
- Per-source fetch state persisted in SQLite table `source_fetch_state`:
  - `next_fetch_at`, `last_fetch_at`, `last_status`, `error_streak`
- Backoff for errors:
  - 401/403/404: 6h cooldown
  - 429/5xx: 5m → 15m → 1h backoff
- Telegram RSSHub group toggle:
  - System setting `rsshub_telegram_enabled` (1/0)
- Disabled channels list:
  - env `RSSHUB_DISABLED_CHANNELS` (default: `rian_ru`)

## RSSHub Mitigation (Service Side)

- Reduce memory/CPU to minimum stable level (256-512MB where possible).
- Avoid verbose logs in production.
- Prefer Railway internal URL via `RSSHUB_MIRROR_URLS` when available.

## Env Defaults

- `RSSHUB_MIN_INTERVAL_SECONDS=900`
- `RSS_MIN_INTERVAL_SECONDS=300`
- `RSSHUB_CONCURRENCY=2`
- `RSSHUB_DISABLED_CHANNELS=rian_ru`
- `RSSHUB_TELEGRAM_ENABLED=true`

## How to Verify

1) Check source scheduling:
   - Ensure `source_fetch_state.next_fetch_at` is updated for RSSHub URLs.
2) Observe RSSHub network traffic:
   - Requests should drop from every tick to ~15m intervals per channel.
3) Toggle Telegram RSSHub group:
   - In SANDBOX admin panel -> Sources -> Telegram toggle.
4) Confirm backoff:
   - Induce 429/5xx, verify `next_fetch_at` increases.

## Expected Impact

- Lower CPU and network usage in PROD.
- Fewer RSSHub calls and reduced RSSHub service load.
- Improved stability during RSSHub outages or throttling.
