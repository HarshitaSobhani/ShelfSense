from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import AppError
from app.models import User
from app.security import decode_session_token

SESSION_COOKIE = "shelfsense_session"
CSRF_COOKIE = "shelfsense_csrf"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

DB = Annotated[Session, Depends(get_db)]


def _user_from_request(request: Request, db: Session) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    via_cookie = True
    if not token:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token, via_cookie = auth[7:].strip(), False
    if not token:
        return None
    payload = decode_session_token(token)
    if not payload:
        return None
    if via_cookie and request.method not in SAFE_METHODS:
        header = request.headers.get("x-csrf-token")
        if not header or header != payload.get("csrf"):
            raise AppError(403, "csrf_failed", "Missing or invalid CSRF token")
    return db.get(User, int(payload["sub"]))


def current_user(request: Request, db: DB) -> User:
    user = _user_from_request(request, db)
    if user is None:
        raise AppError(401, "unauthorized", "Authentication required")
    return user


def optional_user(request: Request, db: DB) -> User | None:
    return _user_from_request(request, db)


def admin_user(user: Annotated[User, Depends(current_user)]) -> User:
    if not user.is_admin:
        raise AppError(403, "forbidden", "Administrator access required")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
OptionalUser = Annotated[User | None, Depends(optional_user)]
AdminUser = Annotated[User, Depends(admin_user)]
