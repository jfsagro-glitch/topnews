from utils.content_quality import compute_simhash, hamming_distance


def test_simhash_near_duplicate_distance():
    base = "Moscow officials announced a new transport policy today."
    similar = "Moscow officials announced a new transport policy this morning."
    a = compute_simhash(base, title="Transport update")
    b = compute_simhash(similar, title="Transport update")
    assert a is not None
    assert b is not None
    assert hamming_distance(a, a) == 0
    assert hamming_distance(a, b) <= 20
