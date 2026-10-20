import secrets
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.config import get_settings

_hasher = PasswordHash.recommended()  # argon2id
ALGO = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _hasher.verify(password, hashed)
    except Exception:
        return False


_DUMMY = None


def dummy_verify(password: str) -> None:
    """Spend comparable time when the email is unknown, to blunt user enumeration by timing."""
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = _hasher.hash("shelfsense-dummy")
    verify_password(password, _DUMMY)


def create_session_token(user_id: int) -> tuple[str, str]:
    s = get_settings()
    csrf = secrets.token_urlsafe(24)
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "csrf": csrf, "iat": now, "exp": now + timedelta(days=s.session_days)}
    return jwt.encode(payload, s.secret_key, algorithm=ALGO), csrf


def decode_session_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=[ALGO])
    except jwt.PyJWTError:
        return None
