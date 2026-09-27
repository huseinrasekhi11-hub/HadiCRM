from app.auth.jwt_handler import create_access_token
from app.auth.jwt_handler import verify_token


def test_access_token_contains_expected_payload():
    token = create_access_token(
        {
            "sub": "1",
            "mobile": "09123456789",
        }
    )

    payload = verify_token(token)

    assert payload["sub"] == "1"
    assert payload["mobile"] == "09123456789"
    assert "exp" in payload


def test_invalid_token_returns_none():
    assert verify_token("invalid.token.value") is None


def test_refresh_token_rejected_as_access_token():
    """
    یک توکن refresh نباید به‌عنوان access token پذیرفته شود، وگرنه
    می‌توان با یک توکن تازه‌سازی (که عمر بسیار طولانی‌تری دارد) وارد
    هر اندپوینتی شد.
    """
    from app.auth.jwt_handler import TOKEN_TYPE_REFRESH, create_refresh_token

    refresh = create_refresh_token({"sub": "1"})

    # به‌عنوان access token رد می‌شود
    assert verify_token(refresh, expected_type="access") is None

    # اما به‌عنوان refresh token خودش معتبر است
    payload = verify_token(refresh, expected_type=TOKEN_TYPE_REFRESH)
    assert payload is not None
    assert payload["sub"] == "1"
    assert payload["type"] == TOKEN_TYPE_REFRESH


def test_access_and_refresh_tokens_have_distinct_jti():
    """هر توکن باید شناسه‌ی یکتای خودش را داشته باشد."""
    token_a = create_access_token({"sub": "1"})
    token_b = create_access_token({"sub": "1"})

    payload_a = verify_token(token_a)
    payload_b = verify_token(token_b)

    assert payload_a["jti"] != payload_b["jti"]

def test_untyped_legacy_token_is_rejected_as_access():
    """Security migration: untyped legacy JWTs must not regain refresh-as-access."""
    import jwt
    from datetime import datetime, timedelta, timezone
    from app.config.settings import settings

    legacy = jwt.encode(
        {
            "sub": "09123456789",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    assert verify_token(legacy, expected_type="access") is None
    assert verify_token(legacy, expected_type="refresh") is None
