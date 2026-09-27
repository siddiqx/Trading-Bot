"""Security and authentication utilities."""

import hmac
from typing import Optional


def verify_webhook_secret(provided_secret: Optional[str], expected_secret: str) -> bool:
    """Safely verify incoming webhook secret against configured secret using constant-time comparison.

    Prevents timing attacks.
    """
    if not provided_secret or not expected_secret:
        return False
    return hmac.compare_digest(provided_secret.strip(), expected_secret.strip())
