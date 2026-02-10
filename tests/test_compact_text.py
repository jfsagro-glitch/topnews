"""Tests for compact_text shrinking long input for AI (token cost reduction)."""
from net.deepseek_client import compact_text


def test_compact_text_short_passthrough():
    assert compact_text("abc", 10) == "abc"


def test_compact_text_long_shrinks():
    s = "a" * 5000
    out = compact_text(s, 900)
    assert len(out) <= 900 + 50
    assert "...\n" in out
