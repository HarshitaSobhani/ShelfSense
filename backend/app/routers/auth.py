from fastapi import APIRouter, Request, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.deps import CSRF_COOKIE, DB, SESSION_COOKIE, CurrentUser
from app.errors import AppError
from app.models import User, UserPreference
from app.schemas import AuthOut, LoginIn, PreferencesIO, RegisterIn, UserOut
from app.security import create_session_token, dummy_verify, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _start_session(response: Response, user: User) -> AuthOut:
    s = get_settings()
    token, csrf = create_session_token(user.id)
    age = s.session_days * 86400
    response.set_cookie(
        SESSION_COOKIE, token, max_age=age, httponly=True, samesite="lax", secure=s.cookie_secure, path="/"
    )
    response.set_cookie(
        CSRF_COOKIE, csrf, max_age=age, httponly=False, samesite="lax", secure=s.cookie_secure, path="/"
    )
    return AuthOut(user=UserOut.model_validate(user), csrf_token=csrf)


@router.post("/register", response_model=AuthOut, status_code=201)
def register(body: RegisterIn, response: Response, db: DB):
    email = body.email.lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise AppError(409, "email_taken", "An account with this email already exists")
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        is_admin=email in get_settings().admin_email_set,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "email_taken", "An account with this email already exists") from None
    return _start_session(response, user)


@router.post("/login", response_model=AuthOut)
def login(body: LoginIn, response: Response, db: DB):
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is None:
        dummy_verify(body.password)
    if user is None or not verify_password(body.password, user.password_hash):
        raise AppError(401, "invalid_credentials", "Incorrect email or password")
    return _start_session(response, user)


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user


prefs_router = APIRouter(prefix="/me/preferences", tags=["preferences"])


def _prefs_out(p: UserPreference | None) -> PreferencesIO:
    if p is None:
        return PreferencesIO()
    return PreferencesIO(
        genres=p.genres,
        moods=p.moods,
        tropes=p.tropes,
        avoid_content_warnings=p.avoid_content_warnings,
        pacing=p.pacing,
    )  # type: ignore[arg-type]


@prefs_router.get("", response_model=PreferencesIO)
def get_prefs(user: CurrentUser, db: DB):
    return _prefs_out(db.get(UserPreference, user.id))


@prefs_router.put("", response_model=PreferencesIO)
def put_prefs(body: PreferencesIO, user: CurrentUser, db: DB, request: Request):
    p = db.get(UserPreference, user.id) or UserPreference(user_id=user.id)
    norm = lambda xs: sorted({x.strip().lower() for x in xs})  # noqa: E731
    p.genres, p.moods, p.tropes = norm(body.genres), norm(body.moods), norm(body.tropes)
    p.avoid_content_warnings = norm(body.avoid_content_warnings)
    p.pacing = body.pacing
    db.add(p)
    db.commit()
    return _prefs_out(p)
