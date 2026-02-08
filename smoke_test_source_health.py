#!/usr/bin/env python3
"""Minimal smoke test for source health and /status helpers."""
from __future__ import annotations

import os
import tempfile

from bot import NewsBot
from db.database import NewsDatabase


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "smoke.db")
        bot = NewsBot()
        bot.db = NewsDatabase(db_path=db_path)
        bot.collector.db = bot.db

        try:
            bot.collector._configured_sources = [
                ("https://example.com/rss.xml", "example.com", "russia", "rss"),
            ]

            bot.db.record_source_event("example.com", "success")
            counts = bot.db.get_source_event_counts(["example.com"], window_hours=24)
            assert counts["example.com"]["success_count"] == 1

            channels_text, sites_text = bot._build_source_status_sections(window_hours=24)
            print(channels_text.strip())
            print(sites_text.strip())
        finally:
            bot.db.close()
            bot.access_db.close()

    print("SMOKE TEST OK")


if __name__ == "__main__":
    main()
