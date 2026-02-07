"""Dry-run ingestion for lenta/ria/yahoo with snapshot checks."""
from __future__ import annotations

import asyncio
import logging
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from db.database import NewsDatabase
from sources.source_collector import SourceCollector

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    db = NewsDatabase(db_path="db/news.db")
    collector = SourceCollector(db=None)

    targets = [
        ("https://lenta.ru/rss/", "lenta.ru", "world"),
        ("https://ria.ru/export/rss2/archive/index.xml", "ria.ru", "world"),
        ("https://news.yahoo.com/rss/", "news.yahoo.com", "world"),
    ]

    all_items: list[dict] = []
    for url, source_name, category in targets:
        logger.info("Collecting %s", source_name)
        items = await collector._collect_from_rss(url, source_name, category)
        all_items.extend(items)
        logger.info("%s items: %d", source_name, len(items))

        for item in items[:3]:
            logger.info(
                "  - %s | date=%s time=%s clean_len=%s checksum=%s",
                item.get("title", "")[:60],
                item.get("published_date"),
                item.get("published_time"),
                len(item.get("clean_text") or ""),
                bool(item.get("checksum")),
            )

    missing_date = [i for i in all_items if not i.get("published_date")]
    missing_text = [i for i in all_items if not i.get("clean_text")]
    missing_checksum = [i for i in all_items if not i.get("checksum")]

    logger.info("Total items: %d", len(all_items))
    logger.info("Missing date: %d", len(missing_date))
    logger.info("Missing clean_text: %d", len(missing_text))
    logger.info("Missing checksum: %d", len(missing_checksum))


if __name__ == "__main__":
    asyncio.run(main())
