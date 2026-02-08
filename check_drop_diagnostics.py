#!/usr/bin/env python3
"""Run one collection cycle and print drop diagnostics."""
from __future__ import annotations

import asyncio
from collections import defaultdict

from bot import NewsBot


def _get_domain(news: dict) -> str:
    url = news.get("url", "")
    if not url:
        return "unknown"
    try:
        from urllib.parse import urlparse

        return urlparse(url).netloc.lower() or "unknown"
    except Exception:
        return "unknown"


async def main() -> None:
    bot = NewsBot()
    news_items = []
    per_source_timeout = 20
    for fetch_url, source_name, category, src_type in bot.collector._configured_sources:
        if source_name == "ria.ru":
            continue
        try:
            if src_type == "rss":
                items = await asyncio.wait_for(
                    bot.collector._collect_from_rss(fetch_url, source_name, category),
                    timeout=per_source_timeout,
                )
            else:
                items = await asyncio.wait_for(
                    bot.collector._collect_from_html(fetch_url, source_name, category),
                    timeout=per_source_timeout,
                )
            news_items.extend(items)
        except asyncio.TimeoutError:
            print(f"Timeout collecting {source_name} ({fetch_url})")
        except asyncio.CancelledError:
            print(f"Cancelled collecting {source_name} ({fetch_url})")
        except Exception as exc:
            print(f"Error collecting {source_name} ({fetch_url}): {exc}")

    total_by_source: dict[str, int] = defaultdict(int)
    kept_by_source: dict[str, int] = defaultdict(int)
    drop_by_source: dict[str, int] = defaultdict(int)

    for news in news_items:
        source = news.get("source", "unknown")
        total_by_source[source] += 1

        ok, reason = bot._should_publish_news(news)
        if ok:
            kept_by_source[source] += 1
        else:
            drop_by_source[source] += 1
            domain = _get_domain(news)
            bot._record_drop_reason(domain, reason)

    configured_sources = [s[1] for s in bot.collector._configured_sources]
    configured_sources = sorted(set(configured_sources))

    print("=" * 60)
    print("DROP DIAGNOSTICS (one collection)")
    print("=" * 60)

    print("\nSources with zero collected items:")
    for src in configured_sources:
        if total_by_source.get(src, 0) == 0:
            print(f"  - {src}")

    print("\nPer-source counts (total / kept / dropped):")
    for src in sorted(total_by_source.keys()):
        print(
            f"  - {src}: {total_by_source[src]} / {kept_by_source.get(src, 0)} / {drop_by_source.get(src, 0)}"
        )

    print("\nDrop reasons summary by domain:")
    for domain, reasons in sorted(bot.drop_counters.items()):
        reason_parts = ", ".join(f"{k}:{v}" for k, v in sorted(reasons.items()))
        print(f"  - {domain}: {reason_parts}")


if __name__ == "__main__":
    asyncio.run(main())
