from db.database import NewsDatabase


def test_checksum_recent():
    db = NewsDatabase(db_path=":memory:")
    db.add_news(
        url="https://example.com/1",
        title="Test title",
        source="example",
        category="russia",
        checksum="abc123",
    )
    assert db.is_checksum_recent("abc123", hours=48)
    assert not db.is_checksum_recent("def456", hours=48)
