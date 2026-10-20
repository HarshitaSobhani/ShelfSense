import asyncio
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.errors import install_error_handlers
from app.routers import admin, auth, books, health, library
from app.services.embeddings import get_embedder

API = "/api/v1"


class SlidingWindow:
    """In-process limiter. For multiple replicas enforce limits at the proxy as well (see docs/DEPLOYMENT.md)."""

    def __init__(self) -> None:
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int, window: float = 60.0) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Load the embedding model at startup (off the event loop) so the first search is not slow.
    # Failure is not fatal: the app runs with keyword search and /health explains why.
    if get_settings().embedding_provider != "none":
        await asyncio.to_thread(get_embedder)
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="ShelfSense API",
        version="0.1.0",
        docs_url=f"{API}/docs",
        openapi_url=f"{API}/openapi.json",
        lifespan=lifespan,
    )
    limiter = SlidingWindow()
    app.state.limiter = limiter
    install_error_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Authorization"],
    )

    @app.middleware("http")
    async def guard(request: Request, call_next):
        request.state.request_id = request.headers.get("x-request-id", "")[:64] or uuid.uuid4().hex[:16]
        ip = request.client.host if request.client else "unknown"

        def reject(status: int, code: str, msg: str):
            r = JSONResponse(
                {"error": {"code": code, "message": msg, "details": None, "request_id": request.state.request_id}},
                status_code=status,
            )
            r.headers["X-Request-ID"] = request.state.request_id
            return r

        if request.method in ("POST", "PUT", "PATCH"):
            cl = request.headers.get("content-length")
            if cl and cl.isdigit() and int(cl) > s.max_body_bytes:
                return reject(413, "payload_too_large", "Request body too large")
        if request.url.path.startswith(f"{API}/auth/") and request.method == "POST":
            if not limiter.allow(f"auth:{ip}", s.auth_rate_limit_per_minute):
                return reject(429, "rate_limited", "Too many authentication attempts; try again shortly")
        elif not limiter.allow(f"all:{ip}", s.rate_limit_per_minute):
            return reject(429, "rate_limited", "Too many requests; slow down")
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    for r in (health.router, auth.router, auth.prefs_router, books.router, library.router, admin.router):
        app.include_router(r, prefix=API)
    return app


app = create_app()
