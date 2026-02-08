"""Environment helpers shared across bot and database logic."""
from __future__ import annotations

import os


def get_app_env() -> str:
    """Return normalized APP_ENV ('prod' or 'sandbox')."""
    raw = (os.getenv("APP_ENV", "prod") or "prod").strip().lower()
    return raw if raw in {"prod", "sandbox"} else "prod"
