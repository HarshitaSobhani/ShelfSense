from fastapi import APIRouter
from sqlalchemy import text

from app.deps import DB
from app.services import vectorstore
from app.services.catalog import stale_embedding_count
from app.services.embeddings import embedder_status

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: DB):
    """Liveness plus honest capability report: semantic search is listed active only if a model is loaded
    and a vector column exists."""
    try:
        db.execute(text("select 1"))
        db_ok = True
    except Exception:
        db_ok = False
    be = vectorstore.backend(db) if db_ok else None
    st = embedder_status()
    cov = vectorstore.coverage(db) if be else {"books": 0, "embedded": 0}
    return {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
        "vector_backend": be,
        "semantic_search": {
            "active": bool(st.available and be and cov["embedded"] > 0),
            "model": st.model,
            "model_loaded": st.available,
            "reason": st.reason,
            "setup": st.setup,
            "indexed_books": cov["embedded"],
            "total_books": cov["books"],
            "stale_embeddings": stale_embedding_count(db) if be else 0,
        },
    }
