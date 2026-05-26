from __future__ import annotations

import hmac
import os


def expected_api_key() -> str | None:
    return os.getenv("AGENT_API_KEY")


def is_auth_enabled() -> bool:
    return bool(expected_api_key())


def verify_api_key(value: str | None) -> bool:
    expected = expected_api_key()
    if not expected:
        return True
    if not value:
        return False
    return hmac.compare_digest(value, expected)


def extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()
