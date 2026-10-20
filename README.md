# ShelfSense

Book discovery by **meaning, mood, themes and reading preferences**, not just genre.

- **Frontend:** React 19 + TypeScript + Vite + Tailwind CSS 4
- **Backend:** Python 3.11+ (tested on 3.13), FastAPI, Pydantic 2, SQLAlchemy 2, Alembic
- **Database:** PostgreSQL 16 + [pgvector](https://github.com/pgvector/pgvector) (plain-array fallback if the extension is unavailable)
- **NLP:** `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions, runs locally on CPU). Setup: [docs/MODEL_SETUP.md](docs/MODEL_SETUP.md)

The core experience needs **no paid service and no API key**. A bundled catalog of 62 real books is seeded locally. Open Library import is optional and keyless.

## What it does

| Area | Details |
| --- | --- |
| Discovery | Browse with pagination/sorting; filter by genre, mood, trope, pacing, year range; hide books carrying chosen content warnings |
| Semantic search | Natural-language query → embedding → pgvector cosine search, blended with a small keyword/tag signal and an exact title/author bonus. Every result carries its ranking factors |
| Honest fallback | If the model or index is missing, search switches to keyword + tag matching and **says so** in the API (`meta.mode_used`, `meta.notice`), the UI, and `/health`. `mode=semantic` returns `503 semantic_unavailable` with setup instructions instead of pretending |
| Similar books | Nearest neighbours of a book's stored vector; metadata (shared tags/author) fallback when a book has no vector |
| Personal recommendations | Taste vector from ratings (5★ +2 … 1★ −2) and saved/reading/completed books, re-ranked with explicit preferences. Completed and rated books are excluded unless `exclude_read=false`; avoided content warnings are a hard filter |
| Explanations | Built only from stored metadata + numeric factors, e.g. “semantic similarity 0.62 to your taste (e.g. “Jane Eyre”); shares atmospheric (mood)” |
| Accounts | Argon2id password hashing, httpOnly session cookie + CSRF header, bearer-token support for API clients |
| Bookshelf | Want to read / Reading / Completed / On hold, progress (page or %), 1–5 ratings, private notes, yearly reading goal |
| Evaluation | Recall@k, Precision@k, MRR, nDCG@k for keyword / semantic / hybrid modes against hand-written judgments, stored per run, shown on `/evaluation` |
| Open Library | Admin import and per-book refresh via `openlibrary.org/search.json` and `/works/{id}.json` |

## Quick start (local, no Docker)

Requirements: Python ≥ 3.11, Node ≥ 20, PostgreSQL 16 with the `vector` extension (or use `docker compose up -d db`).

```bash
cp .env.example .env            # edit values; never commit .env
make venv                       # python venv + backend deps (incl. sentence-transformers, CPU torch) + npm ci
docker compose up -d db         # or point SHELFSENSE_DATABASE_URL at your own Postgres
set -a; . ./.env; set +a
make migrate                    # alembic upgrade head
make seed                       # loads 62 books; embeds them if the model can load
make api                        # http://localhost:8000  (docs: /api/v1/docs)
make web                        # http://localhost:5173  (proxies /api to :8000)
```

The first `seed`/`download-model` downloads ~90 MB from Hugging Face once. Without network access, see the offline options in [docs/MODEL_SETUP.md](docs/MODEL_SETUP.md); the app still works with keyword search.

To make yourself an admin (needed for import / rebuild / running evaluations): set `SHELFSENSE_ADMIN_EMAILS=you@example.com` before registering, or run `python -m app.cli make-admin you@example.com`.

## Docker Compose

```bash
cp .env.example .env            # set POSTGRES_PASSWORD and SHELFSENSE_SECRET_KEY
docker compose up --build       # web: http://localhost:8080, API docs: http://localhost:8000/api/v1/docs
```

The API container applies migrations, seeds the catalog and builds the embedding index on start. The model is cached in the `models` volume. Build with `BUILD_EMBEDDINGS=0` for a keyword-only image. *(The compose file was validated with `docker compose config`; the images could not be built in the authoring sandbox because it has no Docker daemon.)*

## Commands

| Task | Command |
| --- | --- |
| Backend tests | `cd backend && pytest` (needs Postgres+pgvector; see [docs/TESTING.md](docs/TESTING.md)) |
| Frontend tests | `cd frontend && npm test` |
| Lint / types | `make lint typecheck` |
| Production build | `cd frontend && npm run build` |
| Everything | `make check` |
| Rebuild embeddings | `python -m app.cli rebuild-index [--force]` |
| Run evaluation | `python -m app.cli evaluate -k 5` |

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): data model, retrieval and ranking pipeline, security model
- [docs/API.md](docs/API.md): endpoints, error format, examples (`docs/openapi.json` is the generated OpenAPI schema; live docs at `/api/v1/docs`)
- [docs/MODEL_SETUP.md](docs/MODEL_SETUP.md): model download, offline use, versioning, **how to rebuild the index**
- [docs/TESTING.md](docs/TESTING.md): test layout and how to run it
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md): production checklist and steps

## Data and honesty notes

- **Catalog:** titles, authors and first-publication years are real. Descriptions are short original summaries written for this project, *not* publisher blurbs. **Moods, tropes, pacing and content notes are editorial annotations**, not publisher data, and are not exhaustive. Seeded books have no cover URLs and no page counts (so progress is tracked as percent unless you enter pages for an imported book); the UI draws a typographic cover fallback.
- **No synthetic users.** The app ships with no fake ratings or accounts. Personalised recommendations have **not** been evaluated against real users.
- **Evaluation numbers** are from 19 hand-written queries over the 62-book seed catalog, authored by the same people who wrote the tags. They detect regressions and compare modes; they do not prove general quality. Current results are in the report you generated (`python -m app.cli evaluate`) and on `/evaluation`.

## Licence

No licence file has been chosen yet. Add one before publishing.
