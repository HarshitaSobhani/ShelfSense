import json

import httpx
import pytest
from sqlalchemy import func, select

from app.models import Book
from app.routers import admin
from app.services import openlibrary
from tests.conftest import new_client

DOC = {
    "key": "/works/OL1W",
    "title": "Dune",
    "author_name": ["Frank Herbert"],
    "author_key": ["OL2A"],
    "first_publish_year": 1965,
    "cover_i": 123,
    "subject": ["Science fiction", "Ecology", "12345", "Accessible book"],
    "number_of_pages_median": 412,
    "language": ["eng"],
}


def transport(search_status=200, work_status=200, docs=None, work=None, search_body=None):
    def handler(req: httpx.Request) -> httpx.Response:
        assert "ShelfSense" in req.headers["user-agent"]
        if req.url.path == "/search.json":
            if search_body is not None:
                return httpx.Response(search_status, content=search_body)
            return httpx.Response(search_status, json={"docs": docs if docs is not None else [DOC]})
        return httpx.Response(
            work_status,
            json=work
            if work is not None
            else {"description": {"type": "/type/text", "value": "A desert planet saga."}},
        )

    return httpx.MockTransport(handler)


@pytest.fixture
def admin_client(monkeypatch):
    monkeypatch.setenv("SHELFSENSE_ADMIN_EMAILS", "admin@example.com")
    from app.config import get_settings

    get_settings.cache_clear()
    c = new_client("admin@example.com")
    yield c
    monkeypatch.delenv("SHELFSENSE_ADMIN_EMAILS")
    get_settings.cache_clear()
    admin.http_transport = None


def test_parse_doc_maps_fields_and_cleans_subjects():
    d = openlibrary.parse_doc(DOC)
    assert d["open_library_key"] == "OL1W" and d["authors"] == ["Frank Herbert"]
    assert d["genres"] == ["science fiction", "ecology"]  # numeric / accessibility junk dropped
    assert d["cover_url"].endswith("/b/id/123-L.jpg") and d["page_count"] == 412


@pytest.mark.parametrize("bad", [{}, {"key": "/works/X", "title": "T"}, {"title": "T", "author_name": ["A"]}])
def test_parse_doc_rejects_incomplete(bad):
    assert openlibrary.parse_doc(bad) is None


def test_work_description_variants():
    assert openlibrary.work_description({"description": " plain "}) == "plain"
    assert openlibrary.work_description({"description": {"value": "x"}}) == "x"
    assert openlibrary.work_description({"description": {"value": ""}}) is None
    assert openlibrary.work_description({}) is None


def test_import_creates_books_once(admin_client, db, embedder):
    admin.http_transport = transport()
    r = admin_client.post("/api/v1/admin/import/openlibrary", json={"query": "dune", "limit": 5})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imported"] == 1 and body["indexing"]["status"] == "ok" and body["indexing"]["indexed"] == 1
    admin_client.post("/api/v1/admin/import/openlibrary", json={"query": "dune", "limit": 5})  # re-import
    assert db.scalar(select(func.count()).select_from(Book)) == 1
    b = db.scalar(select(Book))
    assert b.source == "openlibrary" and b.description == "A desert planet saga." and b.last_refreshed_at


def test_import_survives_description_failure(admin_client, db):
    admin.http_transport = transport(work_status=500)
    r = admin_client.post("/api/v1/admin/import/openlibrary", json={"query": "dune"})
    assert r.status_code == 200 and r.json()["imported"] == 1 and "description unavailable" in r.json()["warnings"][0]
    assert db.scalar(select(Book.description)) is None  # no invented description


def test_import_skips_incomplete_docs(admin_client):
    admin.http_transport = transport(docs=[{"title": "No author", "key": "/works/OL9W"}, DOC])
    r = admin_client.post("/api/v1/admin/import/openlibrary", json={"query": "dune"})
    assert r.json()["imported"] == 1 and r.json()["skipped_incomplete"] == 1


@pytest.mark.parametrize("kwargs", [dict(search_status=503), dict(search_status=429), dict(search_body=b"<html>")])
def test_import_reports_upstream_failure_as_502(admin_client, kwargs):
    admin.http_transport = transport(**kwargs)
    r = admin_client.post("/api/v1/admin/import/openlibrary", json={"query": "dune"})
    assert r.status_code == 502 and r.json()["error"]["code"] == "external_service_unavailable"


def test_import_network_error_is_502(admin_client):
    def boom(req):
        raise httpx.ConnectError("no route")

    admin.http_transport = httpx.MockTransport(boom)
    r = admin_client.post("/api/v1/admin/import/openlibrary", json={"query": "dune"})
    assert r.status_code == 502 and "ConnectError" in r.json()["error"]["message"]


def test_import_validates_input(admin_client):
    assert admin_client.post("/api/v1/admin/import/openlibrary", json={"query": "d"}).status_code == 422
    assert admin_client.post("/api/v1/admin/import/openlibrary", json={"query": "dune", "limit": 99}).status_code == 422


def test_import_does_not_overwrite_seed_genres(admin_client, db, embedder):
    from app.services.catalog import upsert_book

    upsert_book(
        db,
        {
            "title": "Dune",
            "authors": ["Frank Herbert"],
            "first_publish_year": 1965,
            "genres": ["science fiction", "epic"],
            "moods": ["epic"],
            "open_library_key": "OL1W",
        },
    )
    db.commit()
    admin.http_transport = transport()
    admin_client.post("/api/v1/admin/import/openlibrary", json={"query": "dune"})
    db.expire_all()
    b = db.scalar(select(Book))
    assert b.tag_names("genre") == ["epic", "science fiction"] and b.tag_names("mood") == ["epic"]
    assert db.scalar(select(func.count()).select_from(Book)) == 1


def test_refresh_updates_description_and_reindexes(admin_client, db, embedder):
    admin.http_transport = transport()
    admin_client.post("/api/v1/admin/import/openlibrary", json={"query": "dune"})
    bid = db.scalar(select(Book.id))
    admin.http_transport = transport(work={"title": "Dune", "description": "A new blurb about space and an empire."})
    r = admin_client.post(f"/api/v1/admin/books/{bid}/refresh")
    assert r.status_code == 200 and r.json()["description_updated"] and r.json()["indexing"]["indexed"] == 1
    db.expire_all()
    assert db.get(Book, bid).description.startswith("A new blurb")


def test_refresh_failure_and_non_openlibrary_book(admin_client, db):
    from app.services.catalog import upsert_book

    local = upsert_book(db, {"title": "Local", "authors": ["A"]})
    db.commit()
    assert admin_client.post(f"/api/v1/admin/books/{local.id}/refresh").status_code == 409
    admin.http_transport = transport()
    admin_client.post("/api/v1/admin/import/openlibrary", json={"query": "dune"})
    bid = db.scalar(select(Book.id).where(Book.open_library_key == "OL1W"))
    admin.http_transport = transport(work_status=502)
    assert admin_client.post(f"/api/v1/admin/books/{bid}/refresh").status_code == 502
    assert admin_client.post("/api/v1/admin/books/9999/refresh").status_code == 404


def test_import_without_embedder_reports_unavailable_but_succeeds(admin_client):
    admin.http_transport = transport()
    r = admin_client.post("/api/v1/admin/import/openlibrary", json={"query": "dune"})
    assert r.status_code == 200 and r.json()["indexing"]["status"] == "unavailable" and r.json()["indexing"]["reason"]


_ = json
