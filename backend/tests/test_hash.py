from app.auth.hashing import hash_password
from app.auth.hashing import verify_password


def test_hash_password_verifies_original_password():
    password = "123456"

    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed) is True


def test_hash_password_rejects_wrong_password():
    hashed = hash_password("123456")

    assert verify_password("abcdef", hashed) is False
