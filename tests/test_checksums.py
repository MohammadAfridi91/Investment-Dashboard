from core.utils.checksums import sha256_bytes, sha256_str


def test_sha256_bytes_stable():
    assert sha256_bytes(b"abc") == sha256_bytes(b"abc")
    assert sha256_bytes(b"abc") != sha256_bytes(b"abd")
    assert len(sha256_bytes(b"abc")) == 64


def test_sha256_str_matches_bytes():
    assert sha256_str("hello") == sha256_bytes(b"hello")
