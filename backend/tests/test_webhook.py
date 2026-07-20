from app.notifications.webhook import validate_webhook_url


def test_webhook_blocks_localhost():
    assert validate_webhook_url("http://localhost:8080/hook") is False
    assert validate_webhook_url("http://127.0.0.1:8080/hook") is False


def test_webhook_accepts_public_https():
    assert validate_webhook_url("https://example.com/hook") is True
