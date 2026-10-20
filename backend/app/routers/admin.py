from typing import Any

import httpx
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.deps import DB, AdminUser, CurrentUser
from app.errors import AppError, not_found
from app.models import Book, EvaluationRun
from app.schemas import EvalRunIn, ImportIn
from app.services import openlibrary
from app.services.catalog import index_books, upsert_book
from app.services.evaluation import load_judgments, run_evaluation

router = APIRouter(tags=["admin"])

# tests replace this to inject httpx.MockTransport
http_transport: httpx.BaseTransport | None = None


class RebuildIn(BaseModel):
    force: bool = False


def _ext(e: openlibrary.ExternalServiceError) -> AppError:
    return AppError(502, "external_service_unavailable", e.message, {"upstream_status": e.status})


@router.post("/admin/import/openlibrary")
def import_openlibrary(body: ImportIn, db: DB, _: AdminUser):
    try:
        docs = openlibrary.search_works(body.query, body.limit, http_transport)
    except openlibrary.ExternalServiceError as e:
        raise _ext(e) from e
    imported, skipped, warnings = [], 0, []
    for doc in docs:
        data = openlibrary.parse_doc(doc)
        if data is None:
            skipped += 1
            continue
        try:
            work = openlibrary.fetch_work(data["open_library_key"], http_transport)
            desc = openlibrary.work_description(work)
            if desc:
                data["description"] = desc
        except openlibrary.ExternalServiceError as e:
            warnings.append(f"{data['title']}: description unavailable ({e.message})")
        existing = db.scalar(select(Book).where(Book.open_library_key == data["open_library_key"]))
        if existing is not None and existing.source == "seed":
            data.pop("genres", None)
        book = upsert_book(db, data, source="openlibrary")
        from datetime import UTC, datetime

        book.last_refreshed_at = datetime.now(UTC)
        imported.append(book.id)
    db.commit()
    idx = index_books(db, imported) if imported else {"status": "skipped", "indexed": 0}
    return {
        "imported": len(imported),
        "skipped_incomplete": skipped,
        "book_ids": imported,
        "warnings": warnings,
        "indexing": idx,
    }


@router.post("/admin/books/{book_id}/refresh")
def refresh_book(book_id: int, db: DB, _: AdminUser):
    from datetime import UTC, datetime

    book = db.get(Book, book_id)
    if book is None:
        raise not_found("Book")
    if not book.open_library_key:
        raise AppError(409, "not_refreshable", "Only books imported from Open Library can be refreshed")
    try:
        work = openlibrary.fetch_work(book.open_library_key, http_transport)
    except openlibrary.ExternalServiceError as e:
        raise _ext(e) from e
    data: dict[str, Any] = {"title": work.get("title") or book.title}
    desc = openlibrary.work_description(work)
    if desc:
        data["description"] = desc
    upsert_book(db, {**data, "open_library_key": book.open_library_key}, source=book.source)
    book.last_refreshed_at = datetime.now(UTC)
    db.commit()
    return {"book_id": book.id, "description_updated": bool(desc), "indexing": index_books(db, [book.id])}


@router.post("/admin/embeddings/rebuild")
def rebuild(body: RebuildIn, db: DB, _: AdminUser):
    return index_books(db, None, force=body.force)


@router.get("/evaluation/runs")
def evaluation_runs(db: DB, _: CurrentUser):
    runs = db.scalars(select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(10)).all()
    return {
        "runs": [
            {
                "id": r.id,
                "created_at": r.created_at,
                "k": r.k,
                "catalog_size": r.catalog_size,
                "embedding_model": r.embedding_model,
                "judgments_version": r.judgments_version,
                "results": r.results,
            }
            for r in runs
        ],
        "judgments": {
            "version": load_judgments()["version"],
            "note": load_judgments()["note"],
            "query_count": len(load_judgments()["queries"]),
        },
    }


@router.post("/evaluation/run")
def evaluation_run(body: EvalRunIn, db: DB, _: AdminUser):
    return run_evaluation(db, k=body.k)
