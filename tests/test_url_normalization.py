from utils.content_quality import compute_url_hash, normalize_url


def test_normalize_url_removes_tracking_and_ports():
    url = "https://Example.com:443/path/?utm_source=x&b=2&a=1#frag"
    normalized = normalize_url(url)
    assert normalized == "https://example.com/path?a=1&b=2"
    assert compute_url_hash(url) == compute_url_hash(normalized)
