"""Offline retrieval evaluation against hand-written judgments. Metrics are computed, never assumed."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Book, EvaluationRun
from app.services import vectorstore
from app.services.discovery import search
from app.services.embeddings import get_embedder
from app.services.filters import BookFilters

JUDGMENTS = Path(__file__).resolve().parent.parent / "seed" / "judgments.json"


def load_judgments() -> dict[str, Any]:
    return json.loads(JUDGMENTS.read_text(encoding="utf-8"))


def metrics_for(ranked_ids: list[int], relevant: set[int], k: int) -> dict[str, float]:
    top = ranked_ids[:k]
    hits = [1 if b in relevant else 0 for b in top]
    rel_n = len(relevant)
    recall = sum(hits) / rel_n if rel_n else 0.0
    precision = sum(hits) / k
    mrr = next((1.0 / (i + 1) for i, h in enumerate(hits) if h), 0.0)
    dcg = sum(h / math.log2(i + 2) for i, h in enumerate(hits))
    idcg = sum(1 / math.log2(i + 2) for i in range(min(rel_n, k)))
    return {"recall": recall, "precision": precision, "mrr": mrr, "ndcg": dcg / idcg if idcg else 0.0}


def run_evaluation(db: Session, k: int = 5, persist: bool = True) -> dict[str, Any]:
    j = load_judgments()
    titles = {b.title: b.id for b in db.scalars(select(Book))}
    emb = get_embedder()
    sem_ok = emb is not None and vectorstore.backend(db) is not None
    modes = ["keyword"] + (["semantic", "hybrid"] if sem_ok else [])
    skipped = (
        []
        if sem_ok
        else [{"mode": m, "reason": "embedding model or vector index unavailable"} for m in ("semantic", "hybrid")]
    )
    per_mode: dict[str, Any] = {}
    unresolved: list[str] = []
    for mode in modes:
        rows = []
        for item in j["queries"]:
            rel = {titles[t] for t in item["relevant"] if t in titles}
            unresolved += [t for t in item["relevant"] if t not in titles]
            if not rel:
                continue
            res = search(db, item["q"], BookFilters(), mode=mode, limit=50)
            ids = [h.book.id for h in res.hits]
            rows.append(
                {
                    "q": item["q"],
                    **{kk: round(v, 4) for kk, v in metrics_for(ids, rel, k).items()},
                    "top": [h.book.title for h in res.hits[:k]],
                    "relevant": item["relevant"],
                }
            )
        n = len(rows) or 1
        per_mode[mode] = {
            "mean": {m: round(sum(r[m] for r in rows) / n, 4) for m in ("recall", "precision", "mrr", "ndcg")},
            "queries": rows,
        }
    result = {
        "k": k,
        "modes": per_mode,
        "skipped_modes": skipped,
        "unresolved_titles": sorted(set(unresolved)),
        "query_count": len(j["queries"]),
        "caveat": j["note"],
    }
    if persist:
        db.add(
            EvaluationRun(
                k=k,
                catalog_size=len(titles),
                embedding_model=emb.name if emb else None,
                judgments_version=j["version"],
                results=result,
            )
        )
        db.commit()
    result["judgments_version"] = j["version"]
    result["catalog_size"] = len(titles)
    result["embedding_model"] = emb.name if emb else None
    result["configured_model"] = get_settings().embedding_model
    return result
