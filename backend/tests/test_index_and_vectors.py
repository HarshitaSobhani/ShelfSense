import numpy as np
from sqlalchemy import text

from app.models import Book
from app.services import vectorstore
from app.services.catalog import index_books, stale_embedding_count, upsert_book
from app.services.normalize import build_document, normalize_author, normalize_tags, slugify
from tests.conftest import BOOKS


def test_normalization_helpers():
    assert normalize_tags([" Cozy ", "cozy", "FOUND  Family", ""]) == ["cozy", "found family"]
    assert normalize_author("Brontë, Charlotte") == normalize_author("Bronte Charlotte")
    assert slugify("Rebecca", 1938) == "rebecca-1938" and slugify("Ünïcode: Title!") == "unicode-title"


def test_document_uses_only_available_metadata():
    assert build_document("T", [], None, [], [], [], None) == "T"
    d = build_document("T", ["A"], "Desc.", ["g"], ["m"], ["t"], "slow")
    assert d == "T. by A. Genres: g. Mood: m. Themes and tropes: t. Pacing: slow. Desc."


def test_upsert_is_idempotent_and_updates_tags(db):
    row = dict(BOOKS[0])
    a = upsert_book(db, dict(row))
    b = upsert_book(db, {**row, "moods": ["wistful"]})
    db.commit()
    assert a.id == b.id and db.query(Book).count() == 1
    db.expire_all()
    assert db.get(Book, a.id).tag_names("mood") == ["wistful"]
    assert db.get(Book, a.id).tag_names("genre") == ["cozy mystery"]  # untouched kinds preserved


def test_shared_author_is_one_row(db):
    upsert_book(db, dict(BOOKS[0]))
    upsert_book(db, dict(BOOKS[4]))
    db.commit()
    assert db.execute(text("select count(*) from authors where normalized_name='ada quill'")).scalar() == 1


def test_index_only_embeds_changed_books_and_records_version(db, embedder):
    for b in BOOKS:
        upsert_book(db, dict(b))
    db.commit()
    assert index_books(db) == {"status": "ok", "model": embedder.name, "indexed": 7, "skipped": 0}
    assert index_books(db)["indexed"] == 0
    book = db.query(Book).filter_by(title="Teacup Mornings").one()
    upsert_book(
        db, {"title": "Teacup Mornings", "first_publish_year": 2001, "description": "Now about dragons and magic."}
    )
    db.commit()
    assert index_books(db)["indexed"] == 1
    assert index_books(db, force=True)["indexed"] == 7
    meta = db.execute(
        text("select model_name, model_revision, schema_version, dim from book_embeddings where book_id=:b"),
        {"b": book.id},
    ).one()
    assert tuple(meta) == (embedder.name, "test", 1, 384)


def test_stale_embeddings_detected_when_model_changes(db, embedder):
    for b in BOOKS[:2]:
        upsert_book(db, dict(b))
    db.commit()
    index_books(db)
    assert stale_embedding_count(db) == 2  # configured model differs from the test embedder's name


def test_index_reports_unavailable_without_model(db):
    upsert_book(db, dict(BOOKS[0]))
    db.commit()
    r = index_books(db)
    assert r["status"] == "unavailable" and r["indexed"] == 0 and "disabled" in r["reason"]


def test_cosine_rank_orders_and_handles_zero_vectors():
    q = np.array([1.0, 0.0])
    items = [(1, np.array([0.0, 1.0])), (2, np.array([1.0, 0.1])), (3, np.array([0.0, 0.0]))]
    out = vectorstore.cosine_rank(q, items, 2)
    assert [i for i, _ in out] == [2, 1]  # zero vector scores 0, ties with orthogonal; stable order keeps id 1
    assert out[0][1] > 0.99 and vectorstore.cosine_rank(q, [], 3) == []


def test_array_backend_fallback_matches_pgvector_ranking(db, embedder):
    """When pgvector cannot be installed the migration creates a float8[] column. Exercise that code path
    in a scratch schema and check it ranks like pgvector does."""
    for b in BOOKS:
        upsert_book(db, dict(b))
    db.commit()
    index_books(db)
    ids = [r[0] for r in db.execute(text("select id from books order by id")).all()]
    q = embedder.embed(["warm cozy comfort with tea"])[0]
    expected = vectorstore.nearest(db, q, ids, 5)

    db.execute(text("create schema scratch"))
    db.execute(text("set local search_path to scratch"))
    db.execute(
        text(
            "create table book_embeddings (book_id int primary key, model_name text, model_revision text, "
            "schema_version int, dim int, content_hash text, created_at timestamptz default now(), "
            "embedding double precision[] not null)"
        )
    )
    try:
        assert vectorstore.backend(db) == "array"
        vecs = vectorstore_vectors(db)
        for bid, v in vecs.items():
            vectorstore.upsert(db, bid, v, model="m", revision="r", schema=1, chash="h")
        got = vectorstore.nearest(db, q, ids, 5)
        # ties (equal similarity) may order differently, so compare scores and the untied head
        assert [i for i, _ in got][:2] == [i for i, _ in expected][:2]
        assert all(abs(a[1] - b[1]) < 1e-4 for a, b in zip(got, expected, strict=True))
        assert vectorstore.nearest(db, q, [], 5) == []
    finally:
        db.rollback()


def vectorstore_vectors(db):
    # read vectors from the public schema (pgvector) to copy into the scratch array table
    rows = db.execute(text("select book_id, embedding::text from public.book_embeddings")).all()
    return {r[0]: np.array([float(x) for x in r[1].strip("[]").split(",")], dtype=np.float32) for r in rows}


def test_backend_none_when_column_missing(db):
    db.execute(text("create schema empty_s"))
    db.execute(text("set local search_path to empty_s"))
    assert vectorstore.backend(db) is None
    assert vectorstore.nearest(db, np.array([1.0]), [1], 3) == []
    db.rollback()
