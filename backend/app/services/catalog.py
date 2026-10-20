"""Writing books, authors, and tags; maintaining the embedding index."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Author, Book, BookAuthor, BookTag, Tag
from app.services import vectorstore
from app.services.embeddings import EmbeddingUnavailable, get_embedder
from app.services.normalize import (
    build_document,
    clean_text,
    content_hash,
    normalize_author,
    normalize_tags,
    slugify,
)

log = logging.getLogger("shelfsense.catalog")


def _tag(db: Session, kind: str, name: str) -> Tag:
    t = db.scalar(select(Tag).where(Tag.kind == kind, Tag.name == name))
    if t is None:
        t = Tag(kind=kind, name=name)
        db.add(t)
        db.flush()
    return t


def _author(db: Session, name: str, ol_key: str | None = None) -> Author:
    norm = normalize_author(name)
    a = db.scalar(select(Author).where(Author.normalized_name == norm))
    if a is None:
        a = Author(name=name.strip(), normalized_name=norm, open_library_key=ol_key)
        db.add(a)
        db.flush()
    elif ol_key and not a.open_library_key:
        a.open_library_key = ol_key
    return a


def upsert_book(db: Session, data: dict[str, Any], *, source: str = "seed") -> Book:
    """Insert or update by open_library_key, else by slug. `data` keys: title, authors, description,
    first_publish_year, genres, moods, tropes, content_warnings, pacing, cover_url, page_count,
    language, open_library_key, author_keys. Fields absent from `data` are left unchanged on update."""
    title = clean_text(data["title"])
    if not title:
        raise ValueError("title is required")
    year = data.get("first_publish_year")
    ol_key = data.get("open_library_key")
    book = db.scalar(select(Book).where(Book.open_library_key == ol_key)) if ol_key else None
    slug = slugify(title, year)
    if book is None:
        book = db.scalar(select(Book).where(Book.slug == slug))
    if book is None:
        book = Book(slug=slug, title=title, source=source)
        db.add(book)
    book.title = title
    for f in ("subtitle", "description"):
        if f in data:
            setattr(book, f, clean_text(data[f]))
    for f in ("first_publish_year", "page_count", "language", "cover_url", "pacing", "open_library_key"):
        if f in data and data[f] is not None:
            setattr(book, f, data[f])
    db.flush()

    if "authors" in data:
        keys = data.get("author_keys") or []
        db.execute(delete(BookAuthor).where(BookAuthor.book_id == book.id))
        seen: set[int] = set()
        for pos, name in enumerate(n for n in data["authors"] if n and n.strip()):
            a = _author(db, name, keys[pos] if pos < len(keys) else None)
            if a.id not in seen:
                db.add(BookAuthor(book_id=book.id, author_id=a.id, position=pos))
                seen.add(a.id)
    for kind, key in (
        ("genre", "genres"),
        ("mood", "moods"),
        ("trope", "tropes"),
        ("content_warning", "content_warnings"),
    ):
        if key in data:
            db.execute(
                delete(BookTag).where(
                    BookTag.book_id == book.id,
                    BookTag.tag_id.in_(select(Tag.id).where(Tag.kind == kind)),
                )
            )
            for name in normalize_tags(data[key]):
                db.add(BookTag(book_id=book.id, tag_id=_tag(db, kind, name).id))
    db.flush()
    db.expire(book)
    return book


def document_for(book: Book) -> str:
    return build_document(
        book.title,
        [a.name for a in book.authors],
        book.description,
        book.tag_names("genre"),
        book.tag_names("mood"),
        book.tag_names("trope"),
        book.pacing,
    )


def index_books(db: Session, book_ids: Iterable[int] | None = None, *, force: bool = False) -> dict[str, Any]:
    """Embed books whose stored vector is missing or stale. Never raises when no model is available:
    returns {"status": "unavailable", ...} so callers can report it honestly."""
    s = get_settings()
    emb = get_embedder()
    if emb is None:
        from app.services.embeddings import embedder_status

        st = embedder_status()
        return {"status": "unavailable", "reason": st.reason, "indexed": 0, "skipped": 0}
    if vectorstore.backend(db) is None:
        return {
            "status": "unavailable",
            "reason": "book_embeddings.embedding column missing (run migrations)",
            "indexed": 0,
            "skipped": 0,
        }
    q = select(Book)
    if book_ids is not None:
        q = q.where(Book.id.in_(list(book_ids)))
    books = list(db.scalars(q.order_by(Book.id)))
    existing = {r[0]: r[1] for r in db.execute(text("select book_id, content_hash from book_embeddings")).all()}
    todo: list[tuple[Book, str, str]] = []
    skipped = 0
    for b in books:
        doc = document_for(b)
        h = content_hash(doc, emb.name, s.embedding_schema_version)
        if not force and existing.get(b.id) == h:
            skipped += 1
            continue
        todo.append((b, doc, h))
    try:
        for i in range(0, len(todo), 64):
            chunk = todo[i : i + 64]
            vecs = emb.embed([d for _, d, _ in chunk])
            for (b, _, h), v in zip(chunk, vecs, strict=True):
                vectorstore.upsert(
                    db, b.id, v, model=emb.name, revision=emb.revision, schema=s.embedding_schema_version, chash=h
                )
    except EmbeddingUnavailable as e:  # pragma: no cover
        return {"status": "unavailable", "reason": e.reason, "indexed": 0, "skipped": skipped}
    db.commit()
    return {"status": "ok", "model": emb.name, "indexed": len(todo), "skipped": skipped}


def stale_embedding_count(db: Session) -> int:
    """Embeddings whose model/schema differ from the current configuration."""
    s = get_settings()
    return int(
        db.execute(
            text("select count(*) from book_embeddings where model_name <> :m or schema_version <> :v"),
            {"m": s.embedding_model, "v": s.embedding_schema_version},
        ).scalar_one()
    )
