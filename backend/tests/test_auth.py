from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from tests.conftest import register

A = "/api/v1/auth"


def test_register_login_me_logout(client):
    d = register(client)
    assert d["user"]["email"] == "reader@example.com" and "password" not in str(d)
    assert (
        "httponly"
        in client.post(f"{A}/login", json={"email": "reader@example.com", "password": "correct horse battery"})
        .headers["set-cookie"]
        .lower()
    )
    assert client.get(f"{A}/me").json()["display_name"] == "Reader"
    assert client.post(f"{A}/logout", headers={"X-CSRF-Token": d["csrf_token"]}).status_code == 204
    assert client.get(f"{A}/me").status_code == 401


def test_password_is_hashed_with_argon2(client, db):
    from sqlalchemy import select

    from app.models import User

    register(client)
    assert db.scalar(select(User.password_hash)).startswith("$argon2")


def test_duplicate_email_case_insensitive(client):
    register(client, email="A@Example.com")
    r = client.post(
        f"{A}/register", json={"email": "a@example.com", "password": "another long pass", "display_name": "x"}
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "email_taken"


def test_registration_validation_errors(client):
    r = client.post(f"{A}/register", json={"email": "nope", "password": "short", "display_name": " "})
    body = r.json()
    assert r.status_code == 422 and body["error"]["code"] == "validation_error"
    fields = {d["field"] for d in body["error"]["details"]}
    assert {"email", "password", "display_name"} <= fields
    assert body["error"]["request_id"]


def test_bad_credentials_do_not_reveal_which_part_is_wrong(client):
    register(client)
    a = client.post(f"{A}/login", json={"email": "reader@example.com", "password": "wrong password!"})
    b = client.post(f"{A}/login", json={"email": "ghost@example.com", "password": "wrong password!"})
    assert a.status_code == b.status_code == 401
    assert a.json()["error"]["message"] == b.json()["error"]["message"]


def test_protected_routes_require_auth(client):
    for path in ("/library", "/recommendations", "/me/preferences", "/goals", "/evaluation/runs"):
        assert client.get(f"/api/v1{path}").status_code == 401, path


def test_cookie_mutations_require_csrf_header(client):
    register(client)  # no X-CSRF-Token header set on the client
    r = client.put("/api/v1/me/preferences", json={"genres": ["fantasy"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"


def test_bearer_token_needs_no_csrf(client):
    from app.security import create_session_token

    d = register(client)
    token, _ = create_session_token(d["user"]["id"])
    fresh = TestClient(create_app())
    r = fresh.put("/api/v1/me/preferences", json={"genres": ["Fantasy"]}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["genres"] == ["fantasy"]


def test_tampered_token_rejected(client):
    register(client)
    client.cookies.set("shelfsense_session", "abc.def.ghi")
    assert client.get(f"{A}/me").status_code == 401


def test_admin_endpoints_forbidden_for_regular_users(client, auth):
    assert client.post("/api/v1/admin/embeddings/rebuild", json={}).status_code == 403
    assert client.post("/api/v1/admin/import/openlibrary", json={"query": "dune"}).status_code == 403
    assert client.post("/api/v1/evaluation/run", json={}).status_code == 403


def test_admin_email_allowlist(monkeypatch):
    monkeypatch.setenv("SHELFSENSE_ADMIN_EMAILS", "boss@example.com")
    get_settings.cache_clear()
    try:
        c = TestClient(create_app())
        assert register(c, email="boss@example.com")["user"]["is_admin"] is True
        assert register(TestClient(create_app()), email="other@example.com")["user"]["is_admin"] is False
    finally:
        monkeypatch.delenv("SHELFSENSE_ADMIN_EMAILS")
        get_settings.cache_clear()


def test_auth_rate_limit(monkeypatch):
    monkeypatch.setenv("SHELFSENSE_AUTH_RATE_LIMIT_PER_MINUTE", "3")
    get_settings.cache_clear()
    try:
        c = TestClient(create_app())
        codes = [c.post(f"{A}/login", json={"email": "x@example.com", "password": "pw"}).status_code for _ in range(5)]
        assert codes[:3] == [401, 401, 401] and codes[3:] == [429, 429]
    finally:
        monkeypatch.delenv("SHELFSENSE_AUTH_RATE_LIMIT_PER_MINUTE")
        get_settings.cache_clear()


def test_request_body_limit(client, auth):
    big = {"body": "x" * 70_000}
    r = client.post("/api/v1/books/1/notes", json=big)
    assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"


def test_error_shape_for_unknown_route_and_missing_book(client):
    r = client.get("/api/v1/nope")
    assert r.status_code == 404 and set(r.json()["error"]) == {"code", "message", "details", "request_id"}
    assert client.get("/api/v1/books/999").json()["error"]["code"] == "not_found"
