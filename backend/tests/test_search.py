import pytest

from app.models import Book
from app.services import discovery
from app.services.filters import BookFilters

B = "/api/v1/books"


def titles(r):
    return [i["book"]["title"] for i in r.json()["items"]]


def test_browse_pagination_and_sorting(client, small_catalog_no_embeddings):
    r = client.get(B, params={"page_size": 3, "page": 1})
    assert r.json()["meta"] == {"page": 1, "page_size": 3, "total": 7, "pages": 3}
    assert [b["title"] for b in r.json()["items"]] == sorted(b["title"] for b in r.json()["items"])
    assert len(client.get(B, params={"page_size": 3, "page": 3}).json()["items"]) == 1
    assert client.get(B, params={"page_size": 51}).status_code == 422
    r = client.get(B, params={"sort": "year_asc"}).json()["items"]
    assert r[0]["title"] == "Iron Empire" and r[-1]["title"] == "Nameless Volume"  # NULL year last


def test_filters_genre_mood_trope_pacing_year(client, small_catalog_no_embeddings):
    def t(**p):
        return sorted(b["title"] for b in client.get(B, params={**p, "page_size": 50}).json()["items"])

    assert t(genre="horror") == ["Ashes of the Manor"]
    assert t(mood="cozy") == ["Kisses in the Mist", "Teacup Mornings"]
    assert t(mood="cozy", pacing="slow") == ["Teacup Mornings"]
    assert t(genre=["horror", "romance"]) == ["Ashes of the Manor", "Kisses in the Mist"]  # ANY within kind
    assert t(genre="horror", mood="cozy") == []  # AND across kinds
    assert t(trope="haunted house") == ["Ashes of the Manor"]
    assert t(year_min=2005, year_max=2012) == ["Kisses in the Mist"]
    assert "Nameless Volume" not in t(year_min=1000)  # unknown year never matches a year filter
    assert "Ashes of the Manor" not in t(avoid="violence")
    assert "Iron Empire" not in t(avoid=["war violence"])
    assert client.get(B, params={"pacing": "glacial"}).status_code == 422


def test_filters_are_injection_safe(client, small_catalog_no_embeddings):
    r = client.get(B, params={"genre": "x'; drop table books;--"})
    assert r.status_code == 200 and r.json()["items"] == []
    assert client.get(B).json()["meta"]["total"] == 7


def test_facets(client, small_catalog_no_embeddings):
    f = client.get(f"{B}/facets").json()
    assert {"name": "cozy", "count": 2} in f["moods"]
    assert f["year_min"] == 1975 and f["year_max"] == 2015
    assert {i["name"] for i in f["content_warnings"]} == {"violence", "war violence"}


def test_book_detail_with_missing_metadata(client, small_catalog):
    bid = small_catalog["Nameless Volume"]
    b = client.get(f"{B}/{bid}").json()
    assert b["description"] is None and b["first_publish_year"] is None and b["cover_url"] is None
    assert b["authors"] == ["Fay Stone"] and b["has_embedding"] is True  # title+author still embedded


def test_semantic_search_matches_meaning_not_keywords(client, small_catalog):
    # "astronaut ... galaxy" never appears in the query's words verbatim in Teacup etc.
    r = client.get(f"{B}/search", params={"q": "an astronaut exploring a distant galaxy"})
    body = r.json()
    assert body["meta"]["mode_used"] == "hybrid" and body["meta"]["semantic_available"] is True
    assert titles(r)[0] == "Starship Lullaby"
    top = body["items"][0]
    assert any(f["factor"] == "semantic" for f in top["factors"]) and "semantic similarity" in top["explanation"]


def test_semantic_search_ranks_by_controlled_similarity(client, small_catalog):
    r = client.get(f"{B}/search", params={"q": "warm cozy comfort with tea", "mode": "semantic"})
    ts = titles(r)
    assert ts[0] == "Teacup Mornings" and ts.index("Kisses in the Mist") == 1
    assert "Iron Empire" not in ts  # below the semantic floor: not returned at all
    scores = [i["score"] for i in r.json()["items"]]
    assert scores == sorted(scores, reverse=True)


def test_search_respects_filters(client, small_catalog):
    r = client.get(f"{B}/search", params={"q": "warm cozy comfort", "genre": "romance"})
    assert titles(r) == ["Kisses in the Mist"]
    r = client.get(f"{B}/search", params={"q": "dark haunted murder", "avoid": "violence"})
    assert "Ashes of the Manor" not in titles(r)


def test_keyword_fallback_is_explicit_when_embeddings_unavailable(client, small_catalog_no_embeddings):
    r = client.get(f"{B}/search", params={"q": "haunted manor"})
    m = r.json()["meta"]
    assert m["mode_used"] == "keyword" and m["semantic_available"] is False
    assert "not active" in m["notice"].lower()
    assert titles(r)[0] == "Ashes of the Manor"
    assert all("semantic" not in {f["factor"] for f in i["factors"]} for i in r.json()["items"])


def test_explicit_semantic_mode_errors_when_unavailable(client, small_catalog_no_embeddings):
    r = client.get(f"{B}/search", params={"q": "haunted manor", "mode": "semantic"})
    e = r.json()["error"]
    assert r.status_code == 503 and e["code"] == "semantic_unavailable" and "MODEL_SETUP" in e["details"]["setup"]
    assert client.get(f"{B}/search", params={"q": "haunted manor", "mode": "hybrid"}).status_code == 503


def test_keyword_matches_tags_and_titles(client, small_catalog_no_embeddings):
    cozy = titles(client.get(f"{B}/search", params={"q": "cozy", "mode": "keyword"}))
    assert {"Teacup Mornings", "Kisses in the Mist"} <= set(cozy)
    assert titles(client.get(f"{B}/search", params={"q": "teacup", "mode": "keyword"}))[0] == "Teacup Mornings"
    assert client.get(f"{B}/search", params={"q": "zzzzqqq", "mode": "keyword"}).json()["items"] == []


def test_search_query_validation_and_like_escaping(client, small_catalog_no_embeddings):
    assert client.get(f"{B}/search", params={"q": "a"}).status_code == 422
    assert client.get(f"{B}/search", params={"q": "x" * 301}).status_code == 422
    r = client.get(f"{B}/search", params={"q": "100%_%", "mode": "keyword"})
    assert r.status_code == 200 and r.json()["items"] == []


def test_book_missing_embedding_still_found_and_counted(client, db, small_catalog):
    from sqlalchemy import text

    bid = small_catalog["Teacup Mornings"]
    db.execute(text("delete from book_embeddings where book_id=:b"), {"b": bid})
    db.commit()
    r = client.get(f"{B}/search", params={"q": "teacup", "mode": "auto"})
    assert titles(r)[0] == "Teacup Mornings"  # found lexically
    assert r.json()["meta"]["books_without_embeddings"] == 1
    top = r.json()["items"][0]
    assert {f["factor"] for f in top["factors"]} == {"lexical", "exact_match"}  # no semantic term at all: not penalised


def test_similar_books_use_embeddings_and_explain(client, small_catalog):
    bid = small_catalog["Teacup Mornings"]
    r = client.get(f"{B}/{bid}/similar", params={"limit": 3})
    body = r.json()
    assert body["meta"]["mode_used"] == "embedding"
    assert bid not in [i["book"]["id"] for i in body["items"]]
    assert titles(r)[0] == "Kisses in the Mist"
    assert "Teacup Mornings" in body["items"][0]["explanation"] and "cozy" in body["items"][0]["explanation"]
    assert client.get(f"{B}/9999/similar").status_code == 404


def test_similar_books_metadata_fallback_without_vectors(client, small_catalog_no_embeddings):
    bid = small_catalog_no_embeddings["Teacup Mornings"]
    r = client.get(f"{B}/{bid}/similar")
    m = r.json()["meta"]
    assert m["mode_used"] == "metadata_fallback" and m["semantic_available"] is False and m["notice"]
    ts = titles(r)
    assert "Kisses in the Mist" in ts and "The Dragon's Spell" in ts  # shared mood / same author
    assert "Starship Lullaby" not in ts  # nothing shared


def test_similar_for_book_with_no_metadata_returns_empty_not_error(client, small_catalog_no_embeddings):
    bid = small_catalog_no_embeddings["Nameless Volume"]
    r = client.get(f"{B}/{bid}/similar")
    assert r.status_code == 200 and titles(r) == ["The Dragon's Spell"]  # only shared genre: fantasy


def test_health_reports_semantic_status_honestly(client, small_catalog_no_embeddings):
    h = client.get("/api/v1/health").json()
    assert h["database"] is True and h["vector_backend"] == "pgvector"
    s = h["semantic_search"]
    assert s["active"] is False and s["model_loaded"] is False and s["indexed_books"] == 0 and s["setup"]


def test_health_active_when_indexed(client, small_catalog):
    s = client.get("/api/v1/health").json()["semantic_search"]
    assert s["active"] is True and s["indexed_books"] == 7 and s["total_books"] == 7


@pytest.mark.parametrize("mode", ["keyword", "auto"])
def test_discovery_search_service_direct(db, small_catalog_no_embeddings, mode):
    res = discovery.search(db, "dragon wizard", BookFilters(), mode=mode)
    assert res.hits[0].book.title == "The Dragon's Spell" and res.mode_used == "keyword"


def test_search_does_not_mutate_catalog(db, small_catalog):
    before = db.query(Book).count()
    discovery.search(db, "love", BookFilters())
    assert db.query(Book).count() == before


def test_relative_cutoff_trims_weak_tail(client, small_catalog):
    # only Starship Lullaby is about space; everything else has ~zero similarity and must not pad the list
    r = client.get(f"{B}/search", params={"q": "astronaut starship alien galaxy", "mode": "semantic"})
    assert titles(r) == ["Starship Lullaby"] and r.json()["meta"]["total"] == 1
