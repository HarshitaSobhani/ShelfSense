"""Search, similar-books and personalised recommendations: SQL retrieval + pure ranking."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AppError
from app.models import Author, Book, BookAuthor, BookTag, Rating, ReadingEntry, Tag, UserPreference
from app.services import vectorstore
from app.services.embeddings import embedder_status, get_embedder
from app.services.filters import BookFilters, conditions
from app.services.normalize import normalize_author
from app.services.ranking import (
    Candidate,
    Ranked,
    build_profile,
    jaccard,
    minmax,
    rank,
    tag_token_matches,
    taste_vector,
    tokenize,
)

CANDIDATE_LIMIT = 200


@dataclass
class Hit:
    book: Book
    score: float
    factors: list[dict[str, Any]] = field(default_factory=list)
    explanation: str = ""


@dataclass
class SearchResult:
    hits: list[Hit]
    total: int
    mode_used: str
    semantic_available: bool
    notice: str | None = None
    books_without_embeddings: int = 0
    cold_start: bool = False


def filtered_ids(db: Session, f: BookFilters) -> list[int]:
    return list(db.scalars(select(Book.id).where(*conditions(f)).order_by(Book.id)))


def _load(db: Session, ids: list[int]) -> dict[int, Book]:
    if not ids:
        return {}
    return {b.id: b for b in db.scalars(select(Book).where(Book.id.in_(ids)))}


def _cand(b: Book, semantic: float | None = None, lexical: float = 0.0) -> Candidate:
    return Candidate(
        book_id=b.id,
        author_ids=tuple(a.id for a in b.authors),
        semantic=semantic,
        lexical=lexical,
        genres=frozenset(b.tag_names("genre")),
        moods=frozenset(b.tag_names("mood")),
        tropes=frozenset(b.tag_names("trope")),
        pacing=b.pacing,
    )


def lexical_scores(db: Session, query: str, ids: list[int]) -> tuple[dict[int, float], set[int]]:
    """Returns (0..1 keyword relevance, ids whose title or author contains the query)."""
    exact: set[int] = set()
    tokens = tokenize(query)
    if not ids:
        return {}, exact
    scores: dict[int, float] = {}
    tsq = " | ".join(re.sub(r"[^a-z0-9]", "", t) for t in tokens if re.sub(r"[^a-z0-9]", "", t))
    if tsq:
        rows = db.execute(
            text(
                "select id, ts_rank_cd(search_tsv, to_tsquery('english', :q)) from books "
                "where id = any(:ids) and search_tsv @@ to_tsquery('english', :q)"
            ),
            {"q": tsq, "ids": ids},
        ).all()
        scores = minmax({int(r[0]): float(r[1]) for r in rows})
        scores = {k: 0.6 * v for k, v in scores.items()}
    tags = db.execute(select(Tag.id, Tag.name, Tag.kind).where(Tag.kind != "content_warning")).all()
    matched = [t.id for t in tags if tag_token_matches(tokens, t.name)]
    if matched:
        for bid, n in db.execute(
            select(BookTag.book_id, func.count())
            .where(BookTag.tag_id.in_(matched), BookTag.book_id.in_(ids))
            .group_by(BookTag.book_id)
        ).all():
            scores[bid] = scores.get(bid, 0.0) + min(0.4, 0.2 * n)
    norm = query.strip().lower()
    if len(norm) >= 3:
        word = re.compile(rf"\b{re.escape(norm)}\b")
        esc = norm.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        for bid, title in db.execute(
            select(Book.id, Book.title).where(Book.id.in_(ids), func.lower(Book.title).like(f"%{esc}%", escape="\\"))
        ):
            if word.search(title.lower()):
                exact.add(bid)
    nq = normalize_author(query)
    if len(nq) >= 3:
        word = re.compile(rf"\b{re.escape(nq)}\b")
        esc = nq.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        for bid, name in db.execute(
            select(BookAuthor.book_id, Author.normalized_name)
            .join(Author, Author.id == BookAuthor.author_id)
            .where(BookAuthor.book_id.in_(ids), Author.normalized_name.like(f"%{esc}%", escape="\\"))
        ):
            if word.search(name):
                exact.add(bid)
    return {k: min(1.0, v) for k, v in scores.items() if v > 0}, exact


def explain(book: Book, ranked: Ranked, anchor: str | None = None) -> str:
    """Sentence built only from stored metadata and the numeric factors."""
    bits: list[str] = []
    for f in ranked.factors:
        if f.contribution <= 0:
            continue
        if f.factor == "semantic":
            bits.append(f"semantic similarity {f.value:.2f}" + (f" to {anchor}" if anchor else " to your query"))
        elif f.factor in ("genre", "mood", "trope") and f.evidence.startswith("shares "):
            bits.append(f"{f.evidence} ({f.factor})")
        elif f.factor == "lexical":
            bits.append("keyword match")
        elif f.factor == "pacing" and f.value:
            bits.append(f"{book.pacing} pacing")
    return "Ranked because: " + "; ".join(bits) if bits else "Ranked on limited metadata."


def search(
    db: Session,
    q: str,
    filters: BookFilters,
    mode: str = "auto",
    limit: int = CANDIDATE_LIMIT,
) -> SearchResult:
    ids = filtered_ids(db, filters)
    emb = get_embedder()
    st = embedder_status()
    be = vectorstore.backend(db)
    sem_ok = emb is not None and be is not None
    notice = None
    if mode == "semantic" and not sem_ok:
        raise AppError(
            503,
            "semantic_unavailable",
            "Semantic search is unavailable: " + (st.reason or "no vector index"),
            {"setup": st.setup},
        )
    if mode == "auto":
        mode_used = "hybrid" if sem_ok else "keyword"
        if not sem_ok:
            notice = (
                "Semantic search is not active (" + (st.reason or "no vector index") + "). "
                "Showing keyword and metadata matches only."
            )
    else:
        mode_used = mode
    if mode_used == "hybrid" and not sem_ok:
        raise AppError(
            503, "semantic_unavailable", "Hybrid search needs embeddings: " + (st.reason or ""), {"setup": st.setup}
        )

    sims: dict[int, float] = {}
    if mode_used in ("hybrid", "semantic"):
        assert emb is not None
        qv = emb.embed([q])[0]
        floor = get_settings().min_semantic_score
        sims = {i: v for i, v in vectorstore.nearest(db, qv, ids, limit) if v >= floor}
    lex: dict[int, float] = {}
    exact: set[int] = set()
    if mode_used in ("hybrid", "keyword"):
        lex, exact = lexical_scores(db, q, ids)
    embedded: set[int] = set()
    if sem_ok and mode_used == "hybrid":
        embedded = {
            int(r[0])
            for r in db.execute(text("select book_id from book_embeddings where book_id = any(:i)"), {"i": ids}).all()
        }
    cand_ids = list(set(sims) | set(lex) | exact)
    books = _load(db, cand_ids)
    cands = []
    for i in cand_ids:
        if i not in books:
            continue
        # embedded but below the similarity floor counts as dissimilar (0.0), not as "unknown"
        sem = sims.get(i, 0.0 if i in embedded else None)
        c = _cand(books[i], sem, lex.get(i, 0.0))
        c.exact = i in exact
        cands.append(c)
    lw = get_settings().hybrid_lexical_weight
    weights = (
        {"semantic": 1.0}
        if mode_used == "semantic"
        else ({"lexical": 1.0} if mode_used == "keyword" else {"semantic": 1 - lw, "lexical": lw})
    )
    ranked = rank(
        cands, None, semantic_available=sem_ok and mode_used != "keyword", author_repeat_penalty=0.0, weights=weights
    )
    if ranked and mode_used in ("hybrid", "semantic"):
        best = ranked[0].score
        ranked = [r for r in ranked if r.score >= get_settings().search_relative_cutoff * best]
    without = 0
    if sem_ok and mode_used != "keyword":
        without = len(ids) - int(
            db.execute(text("select count(*) from book_embeddings where book_id = any(:i)"), {"i": ids}).scalar_one()
        )
    hits = [
        Hit(books[r.book_id], r.score, [f.as_dict() for f in r.factors], explain(books[r.book_id], r))
        for r in ranked[:limit]
    ]
    return SearchResult(hits, len(hits), mode_used, sem_ok, notice, max(0, without))


def similar(db: Session, book: Book, limit: int = 8) -> SearchResult:
    ids = [i for i in filtered_ids(db, BookFilters(exclude_ids={book.id}))]
    vecs = vectorstore.get_vectors(db, [book.id])
    src = vecs.get(book.id)
    src_c = _cand(book)
    profile = build_profile([(1.0, src_c.genres, src_c.moods, src_c.tropes)])
    sims: dict[int, float] = {}
    method = "metadata_fallback"
    notice = "This book has no stored embedding; similarity uses shared genres, moods and tropes only."
    if src is not None:
        sims = dict(vectorstore.nearest(db, src, ids, CANDIDATE_LIMIT))
        method, notice = "embedding", None  # type: ignore[assignment]
    books = _load(db, ids)
    cands = []
    for i, b in books.items():
        c = _cand(b, sims.get(i))
        shared_author = set(c.author_ids) & set(src_c.author_ids)
        if src is None and not (
            jaccard(c.genres | c.moods | c.tropes, src_c.genres | src_c.moods | src_c.tropes) or shared_author
        ):
            continue
        cands.append(c)
    ranked = rank(cands, profile, semantic_available=src is not None, author_repeat_penalty=0.03)
    hits = []
    for r in ranked[:limit]:
        b = books[r.book_id]
        e = explain(b, r, anchor=book.title)
        if {a.id for a in b.authors} & {a.id for a in book.authors}:
            e += "; same author"
        hits.append(Hit(b, r.score, [f.as_dict() for f in r.factors], e))
    return SearchResult(hits, len(hits), method, src is not None, notice)


# --- personalised recommendations ---------------------------------------------------------

RATING_WEIGHT = {5: 2.0, 4: 1.0, 3: 0.0, 2: -1.0, 1: -2.0}
SHELF_WEIGHT = {"want_to_read": 0.75, "reading": 0.75, "completed": 0.75, "on_hold": 0.0}


def user_signals(db: Session, user_id: int) -> tuple[dict[int, float], set[int], set[int]]:
    """(book_id -> signal weight, completed ids, rated ids). A rating overrides the shelf signal."""
    weights: dict[int, float] = {}
    completed: set[int] = set()
    rated: set[int] = set()
    for e in db.scalars(select(ReadingEntry).where(ReadingEntry.user_id == user_id)):
        weights[e.book_id] = SHELF_WEIGHT[e.status]
        if e.status == "completed":
            completed.add(e.book_id)
    for r in db.scalars(select(Rating).where(Rating.user_id == user_id)):
        weights[r.book_id] = RATING_WEIGHT[r.value]
        rated.add(r.book_id)
    return weights, completed, rated


def recommend(
    db: Session,
    user_id: int,
    filters: BookFilters,
    *,
    exclude_read: bool = True,
    limit: int = 20,
) -> SearchResult:
    weights, completed, rated = user_signals(db, user_id)
    pref = db.get(UserPreference, user_id)
    exclude = set(filters.exclude_ids)
    if exclude_read:
        exclude |= completed | rated
    if pref and pref.avoid_content_warnings:
        filters.exclude_content_warnings = sorted(
            set(filters.exclude_content_warnings) | set(pref.avoid_content_warnings)
        )
    filters.exclude_ids = exclude
    ids = filtered_ids(db, filters)

    signal_books = _load(db, [b for b, w in weights.items() if w != 0])
    wb = [
        (
            weights[b.id],
            frozenset(b.tag_names("genre")),
            frozenset(b.tag_names("mood")),
            frozenset(b.tag_names("trope")),
        )
        for b in signal_books.values()
    ]
    profile = build_profile(
        wb,
        pref.genres if pref else [],
        pref.moods if pref else [],
        pref.tropes if pref else [],
        pref.pacing if pref else None,
    )
    emb_ok = vectorstore.backend(db) is not None
    vecs = vectorstore.get_vectors(db, list(signal_books)) if emb_ok else {}
    tv = taste_vector([(weights[i], v) for i, v in vecs.items()]) if vecs else None
    if profile.is_empty() and tv is None:
        return SearchResult(
            [],
            0,
            "cold_start",
            tv is not None,
            "Rate or save a few books, or set preferences, to get recommendations.",
            cold_start=True,
        )
    sims: dict[int, float] = {}
    if tv is not None:
        sims = dict(vectorstore.nearest(db, tv, ids, CANDIDATE_LIMIT))
    books = _load(db, ids if tv is None else list(sims) + [i for i in ids if i not in sims])
    cands = [_cand(b, sims.get(b.id)) for b in books.values()]
    if tv is None:
        # metadata-only: keep books that share at least one profile tag
        cands = [
            c
            for c in cands
            if any(
                t in profile.genres or t in profile.moods or t in profile.tropes
                for t in (c.genres | c.moods | c.tropes)
            )
        ]
    ranked = rank(cands, profile, semantic_available=tv is not None)
    anchors = sorted(((weights[i], signal_books[i].title) for i in vecs if weights[i] > 0), reverse=True)
    anchor = anchors[0][1] if anchors else None
    hits = [
        Hit(
            books[r.book_id],
            r.score,
            [f.as_dict() for f in r.factors],
            explain(books[r.book_id], r, anchor=f"your taste (e.g. “{anchor}”)" if anchor else "your taste"),
        )
        for r in ranked[:limit]
    ]
    method = "embedding+metadata" if tv is not None else "metadata_only"
    notice = None
    if tv is None:
        notice = (
            "Recommendations use your preferences and the tags of books you rated or saved. "
            "Embedding similarity is not active, so semantic taste matching is skipped."
        )
    return SearchResult(hits, len(hits), method, tv is not None, notice)
