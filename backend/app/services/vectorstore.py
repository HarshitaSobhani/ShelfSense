"""Vector storage over pgvector with a plain-array fallback (cosine computed in numpy)."""

from __future__ import annotations

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session


def backend(db: Session) -> str | None:
    """'pgvector' | 'array' | None when the column is missing."""
    udt = db.execute(
        text(
            "select udt_name from information_schema.columns "
            "where table_name='book_embeddings' and column_name='embedding' and table_schema=current_schema()"
        )
    ).scalar()
    if udt == "vector":
        return "pgvector"
    if udt == "_float8":
        return "array"
    return None


def _lit(v: np.ndarray) -> str:
    return "[" + ",".join(f"{float(x):.7g}" for x in v) + "]"


def upsert(db: Session, book_id: int, vec: np.ndarray, *, model: str, revision: str, schema: int, chash: str) -> None:
    be = backend(db)
    cast = "CAST(:v AS vector)" if be == "pgvector" else "CAST(:v AS float8[])"
    val = _lit(vec) if be == "pgvector" else [float(x) for x in vec]
    db.execute(
        text(
            f"""insert into book_embeddings (book_id, model_name, model_revision, schema_version, dim,
                    content_hash, embedding)
                values (:b, :m, :r, :s, :d, :h, {cast})
                on conflict (book_id) do update set model_name=:m, model_revision=:r, schema_version=:s,
                    dim=:d, content_hash=:h, embedding={cast}, created_at=now()"""
        ),
        {"b": book_id, "m": model, "r": revision, "s": schema, "d": len(vec), "h": chash, "v": val},
    )


def nearest(db: Session, query: np.ndarray, ids: list[int], limit: int) -> list[tuple[int, float]]:
    """Cosine similarity of `query` against stored vectors for `ids`, best first.
    Books without a stored vector are simply absent from the result."""
    if not ids:
        return []
    be = backend(db)
    if be == "pgvector":
        rows = db.execute(
            text(
                "select book_id, 1 - (embedding <=> CAST(:q AS vector)) as sim from book_embeddings "
                "where book_id = any(:ids) order by embedding <=> CAST(:q AS vector) limit :n"
            ),
            {"q": _lit(query), "ids": ids, "n": limit},
        ).all()
        return [(int(r[0]), float(r[1])) for r in rows]
    if be == "array":
        rows = db.execute(
            text("select book_id, embedding from book_embeddings where book_id = any(:ids)"), {"ids": ids}
        ).all()
        return cosine_rank(query, [(int(r[0]), np.asarray(r[1], dtype=np.float32)) for r in rows], limit)
    return []


def cosine_rank(query: np.ndarray, items: list[tuple[int, np.ndarray]], limit: int) -> list[tuple[int, float]]:
    if not items:
        return []
    q = query / (np.linalg.norm(query) or 1.0)
    mat = np.vstack([v for _, v in items])
    norms = np.linalg.norm(mat, axis=1)
    norms[norms == 0] = 1.0
    sims = (mat / norms[:, None]) @ q
    order = np.argsort(-sims, kind="stable")[:limit]
    return [(items[i][0], float(sims[i])) for i in order]


def get_vectors(db: Session, ids: list[int]) -> dict[int, np.ndarray]:
    if not ids:
        return {}
    be = backend(db)
    if be is None:
        return {}
    rows = db.execute(
        text("select book_id, embedding::text from book_embeddings where book_id = any(:ids)"), {"ids": ids}
    ).all()
    out: dict[int, np.ndarray] = {}
    for bid, raw in rows:
        out[int(bid)] = np.array([float(x) for x in raw.strip("[]{}").split(",")], dtype=np.float32)
    return out


def coverage(db: Session) -> dict[str, int]:
    total = db.execute(text("select count(*) from books")).scalar_one()
    embedded = db.execute(text("select count(*) from book_embeddings")).scalar_one()
    return {"books": int(total), "embedded": int(embedded)}
