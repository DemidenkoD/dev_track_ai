"""Password verification + JWT issuing/verification (HS256 via SECRET_KEY).

Single predefined account: credentials are validated against ADMIN_USERNAME /
ADMIN_PASSWORD from config. There is no registration endpoint.
"""

import secrets
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import get_settings

ALGORITHM = "HS256"


def verify_credentials(username: str, password: str) -> bool:
    """Constant-time comparison against the single predefined account."""
    settings = get_settings()
    user_ok = secrets.compare_digest(username, settings.ADMIN_USERNAME)
    pass_ok = secrets.compare_digest(password, settings.ADMIN_PASSWORD)
    return user_ok and pass_ok


def create_access_token(username: str, role: str = "reviewer") -> tuple[str, int]:
    """Issue a JWT; returns (token, expires_in_seconds)."""
    settings = get_settings()
    expires_in = settings.access_token_expire_seconds
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)
    return token, expires_in


def decode_access_token(token: str) -> dict:
    """Verify signature + expiry; raises jwt.PyJWTError on failure."""
    settings = get_settings()
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
