# Deployment

ShelfSense is two stateless containers (API, static web) plus PostgreSQL with pgvector. Nothing here has been deployed by the authors; follow and adapt.

## Checklist

- [ ] PostgreSQL 16 with `vector` available (managed options with pgvector: Neon, Supabase, RDS/Aurora PostgreSQL, Cloud SQL, or the `pgvector/pgvector:pg16` image).
- [ ] `SHELFSENSE_ENVIRONMENT=production`, a random `SHELFSENSE_SECRET_KEY` (≥ 32 bytes), `SHELFSENSE_COOKIE_SECURE=true` (HTTPS only).
- [ ] `SHELFSENSE_CORS_ORIGINS` = your public web origin (not needed if web and API share an origin through the proxy, as in the provided nginx config).
- [ ] `SHELFSENSE_OPENLIBRARY_CONTACT` = a real contact address.
- [ ] Decide on semantic search: bake the model into the image / mount a cache volume (`HF_HOME`), or run with `SHELFSENSE_EMBEDDING_PROVIDER=none`.
- [ ] Terminate TLS at a proxy/load balancer; enforce a request-body limit there too; add rate limiting at the proxy if you run more than one API replica (the built-in limiter is per process).
- [ ] Back up the database (user data, ratings, notes). Embeddings can be rebuilt from book text.
- [ ] Do not expose PostgreSQL publicly.

## Steps: single host with Docker Compose

```bash
git clone <repo> && cd ShelfSense
cp .env.example .env
#   set POSTGRES_PASSWORD, SHELFSENSE_SECRET_KEY, SHELFSENSE_ENVIRONMENT=production,
#   SHELFSENSE_COOKIE_SECURE=true, SHELFSENSE_ADMIN_EMAILS=<you>, SHELFSENSE_OPENLIBRARY_CONTACT=<you>
docker compose up -d --build
docker compose logs -f api         # wait for "Application startup complete"; first start downloads the model into the `models` volume
curl -s localhost:8000/api/v1/health | jq .semantic_search
```

Put a TLS-terminating reverse proxy (Caddy, nginx, Traefik, a cloud load balancer) in front of the `web` service (port 8080 by default; change the compose port mapping and drop the `127.0.0.1` binding only if you intend to expose it directly). The `web` container proxies `/api/` to the API, so browsers use one origin.

Register the account whose email is in `SHELFSENSE_ADMIN_EMAILS`, then open **Evaluation → Administrator tools** to run the evaluation or import books.

## Steps: separate services (PaaS)

1. **Database:** create PostgreSQL ≥ 14 with pgvector; set `SHELFSENSE_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db`.
2. **API:** build `backend/Dockerfile` (or `pip install "backend[embeddings]"`), run `alembic upgrade head` as a release/pre-start step, then `python -m app.cli seed` once, then `uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers`. Mount a persistent volume at `HF_HOME` for the model cache. Health check: `GET /api/v1/health`.
3. **Web:** `cd frontend && npm ci && npm run build`; serve `dist/` from any static host with an SPA fallback to `index.html`, and route `/api/*` to the API (same origin keeps cookies simple). Cross-origin deployments are not supported out of the box (cookies are `SameSite=Lax`); keep web and API on one origin.

## Upgrades

`docker compose up -d --build` re-runs migrations on start. After changing model settings, see *Versioning and rebuilding* in [MODEL_SETUP.md](MODEL_SETUP.md).

## Operational notes

- Memory: the API process with the model loaded measured ≈ 0.7 GB RSS in development (CPU torch). Keyword-only (`EMBEDDING_PROVIDER=none`) is far smaller.
- The model is loaded at API startup (a few seconds); if loading fails the API still starts and `/health` explains why.
- `/api/v1/health` is safe for liveness probes; `semantic_search.active=false` is a degraded-but-working state, not an outage.
