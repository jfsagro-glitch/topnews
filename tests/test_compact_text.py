from net.deepseek_client import compact_text


def test_compact_text_start_mid_end():
    text = "START-" + "a" * 200 + "-MIDDLE-" + "b" * 200 + "-END"
    compacted = compact_text(text, max_chars=80, strategy="start_mid_end")
    assert len(compacted) <= 80
    assert "START" in compacted
    assert "END" in compacted


def test_compact_text_plain_short():
    text = "Short text"
    compacted = compact_text(text, max_chars=80, strategy="start_mid_end")
    assert compacted == text
