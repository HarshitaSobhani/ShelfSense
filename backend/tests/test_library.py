from datetime import date

from app.models import Book
from tests.conftest import new_client

L = "/api/v1/library"


def test_add_duplicate_and_remove(client, auth, small_catalog_no_embeddings):
    bid = small_catalog_no_embeddings["Teacup Mornings"]
    r = client.post(L, json={"book_id": bid, "status": "want_to_read"})
    assert r.status_code == 201 and r.json()["status"] == "want_to_read"
    dup = client.post(L, json={"book_id": bid, "status": "reading"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "already_in_library"
    assert client.get(L).json()["meta"]["total"] == 1
    assert client.delete(f"{L}/{bid}").status_code == 204
    assert client.delete(f"{L}/{bid}").status_code == 404
    assert client.get(L).json()["meta"]["total"] == 0


def test_add_unknown_book_and_invalid_status(client, auth):
    assert client.post(L, json={"book_id": 999, "status": "reading"}).status_code == 404
    assert client.post(L, json={"book_id": 1, "status": "bogus"}).status_code == 422


def test_status_transitions_set_dates_and_progress(client, auth, small_catalog_no_embeddings):
    bid = small_catalog_no_embeddings["Teacup Mornings"]
    client.post(L, json={"book_id": bid})
    r = client.put(f"{L}/{bid}/status", json={"status": "reading"}).json()
    assert r["started_at"] == date.today().isoformat() and r["finished_at"] is None
    r = client.put(f"{L}/{bid}/status", json={"status": "completed"}).json()
    assert r["progress_percent"] == 100 and r["finished_at"] == date.today().isoformat()
    r = client.put(f"{L}/{bid}/status", json={"status": "on_hold"}).json()
    assert r["finished_at"] is None and r["status"] == "on_hold"
    assert client.put(f"{L}/12345/status", json={"status": "reading"}).status_code == 404


def test_progress_by_pages_percent_and_completion(client, auth, db, small_catalog_no_embeddings):
    bid = small_catalog_no_embeddings["Teacup Mornings"]
    db.get(Book, bid).page_count = 200
    db.commit()
    client.post(L, json={"book_id": bid})
    r = client.patch(f"{L}/{bid}/progress", json={"current_page": 50}).json()
    assert (r["progress_percent"], r["status"]) == (25, "reading")
    r = client.patch(f"{L}/{bid}/progress", json={"progress_percent": 50}).json()
    assert r["current_page"] == 100
    bad = client.patch(f"{L}/{bid}/progress", json={"current_page": 201})
    assert bad.status_code == 422
    assert client.patch(f"{L}/{bid}/progress", json={}).status_code == 422
    assert client.patch(f"{L}/{bid}/progress", json={"progress_percent": 101}).status_code == 422
    r = client.patch(f"{L}/{bid}/progress", json={"current_page": 200}).json()
    assert r["status"] == "completed" and r["finished_at"]


def test_progress_without_known_page_count(client, auth, small_catalog_no_embeddings):
    bid = small_catalog_no_embeddings["Teacup Mornings"]
    client.post(L, json={"book_id": bid})
    r = client.patch(f"{L}/{bid}/progress", json={"current_page": 40}).json()
    assert r["current_page"] == 40 and r["progress_percent"] == 0


def test_list_filters_pagination_and_counts(client, auth, small_catalog_no_embeddings):
    ids = list(small_catalog_no_embeddings.values())
    for i, bid in enumerate(ids[:5]):
        client.post(
            L, json={"book_id": bid, "status": ["want_to_read", "reading", "completed", "on_hold", "reading"][i]}
        )
    r = client.get(L, params={"status": "reading"}).json()
    assert r["meta"]["total"] == 2 and r["counts"] == {"want_to_read": 1, "reading": 2, "completed": 1, "on_hold": 1}
    p = client.get(L, params={"page_size": 2, "page": 3}).json()
    assert len(p["items"]) == 1 and p["meta"]["pages"] == 3
    assert client.get(L, params={"page_size": 1000}).status_code == 422


def test_ratings_upsert_validate_delete_and_show_in_library(client, auth, small_catalog_no_embeddings):
    bid = small_catalog_no_embeddings["Teacup Mornings"]
    url = f"/api/v1/books/{bid}/rating"
    assert client.put(url, json={"value": 5}).json()["value"] == 5
    assert client.put(url, json={"value": 3}).json()["value"] == 3
    assert client.put(url, json={"value": 6}).status_code == 422
    assert client.put(url, json={"value": 0}).status_code == 422
    client.post(L, json={"book_id": bid})
    assert client.get(L).json()["items"][0]["rating"] == 3
    assert client.get(f"/api/v1/me/books/{bid}").json()["rating"] == 3
    assert client.delete(url).status_code == 204
    assert client.delete(url).status_code == 404
    assert client.put("/api/v1/books/9999/rating", json={"value": 4}).status_code == 404


def test_notes_crud_and_privacy(client, auth, small_catalog_no_embeddings):
    bid = small_catalog_no_embeddings["Teacup Mornings"]
    n = client.post(f"/api/v1/books/{bid}/notes", json={"body": "lovely opening"})
    assert n.status_code == 201
    nid = n.json()["id"]
    assert client.post(f"/api/v1/books/{bid}/notes", json={"body": "   "}).status_code == 422
    assert client.put(f"/api/v1/notes/{nid}", json={"body": "edited"}).json()["body"] == "edited"

    other = new_client("other@example.com")
    assert other.get(f"/api/v1/books/{bid}/notes").json() == []
    assert other.put(f"/api/v1/notes/{nid}", json={"body": "hijack"}).status_code == 404
    assert other.delete(f"/api/v1/notes/{nid}").status_code == 404
    assert client.get(f"/api/v1/books/{bid}/notes").json()[0]["body"] == "edited"
    assert client.delete(f"/api/v1/notes/{nid}").status_code == 204


def test_library_is_isolated_between_users(client, auth, small_catalog_no_embeddings):
    bid = small_catalog_no_embeddings["Teacup Mornings"]
    client.post(L, json={"book_id": bid})
    other = new_client("other@example.com")
    assert other.get(L).json()["meta"]["total"] == 0
    assert other.put(f"{L}/{bid}/status", json={"status": "reading"}).status_code == 404
    assert other.patch(f"{L}/{bid}/progress", json={"progress_percent": 10}).status_code == 404
    assert other.post(L, json={"book_id": bid}).status_code == 201  # same book, different user: allowed


def test_reading_goal_counts_completed_in_year(client, auth, small_catalog_no_embeddings):
    ids = list(small_catalog_no_embeddings.values())
    year = date.today().year
    assert client.get("/api/v1/goals").json() == {"year": year, "target_books": None, "completed": 0}
    for bid in ids[:2]:
        client.post(L, json={"book_id": bid, "status": "completed"})
    client.post(L, json={"book_id": ids[2], "status": "reading"})
    r = client.put("/api/v1/goals", json={"target_books": 12}).json()
    assert (r["target_books"], r["completed"]) == (12, 2)
    assert client.put("/api/v1/goals", json={"target_books": 0}).status_code == 422
    assert client.get("/api/v1/goals", params={"year": 1850}).status_code == 422
    assert client.get("/api/v1/goals", params={"year": year - 1}).json()["completed"] == 0
