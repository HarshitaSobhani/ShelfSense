# Testing

## Backend (pytest)

Needs PostgreSQL with the `vector` extension. With Docker: `docker compose up -d db` (an init script creates `shelfsense_test`).
Otherwise create the database yourself and point `SHELFSENSE_TEST_DATABASE_URL` at it, e.g.:

```bash
export SHELFSENSE_TEST_DATABASE_URL=postgresql+psycopg://shelfsense:<password>@localhost:5432/shelfsense_test
cd backend && pytest            # also: pytest --cov=app
ruff check . && ruff format --check . && mypy app
```

The suite **drops and recreates the `public` schema of the test database**, runs `alembic upgrade head` (so migrations are tested), and truncates tables between tests. Never point it at real data.

Tests never download a model. They inject `ControlledEmbedder` (tests/conftest.py), a deterministic keyword-axis embedder, so ranking assertions are exact. It is a test double, **not** a language model, so these tests verify the pipeline, not semantic quality. Real model quality is measured separately with `python -m app.cli evaluate`.

| File | Covers |
| --- | --- |
| `test_auth.py` | registration/login/logout, hashing, duplicate email, validation errors, CSRF, bearer tokens, admin-only routes, rate limit, body limit, error shape |
| `test_library.py` | shelf add/duplicate/remove, status transitions, progress, ratings, private notes, user isolation, goals |
| `test_search.py` | browse pagination/sorting, every filter, injection safety, facets, semantic ranking, filters + search, keyword fallback, explicit-semantic 503, missing description/embedding, similar-books (embedding + metadata fallback), health |
| `test_ranking.py` | pure ranking on small controlled datasets: weights, renormalisation, diversity, ties, taste vectors |
| `test_recommendations.py` | cold start, read/rated exclusion, `exclude_read=false`, low ratings, preferences, avoided warnings, metadata-only fallback, per-user isolation |
| `test_openlibrary.py` | parsing, import/re-import without duplicates, description failures, 429/5xx/invalid JSON/network errors → 502, refresh, seed protection (uses `httpx.MockTransport`; no network) |
| `test_index_and_vectors.py` | normalisation, idempotent upsert, incremental indexing, stale detection, unavailable model, array-backend fallback vs pgvector |
| `test_evaluation.py` | metric formulas, judgments integrity, keyword-only run when embeddings are missing, three-mode run, permissions |

## Frontend (Vitest + React Testing Library)

```bash
cd frontend && npm test && npm run lint && npm run typecheck && npm run build
```

`fetch` is mocked per test (`src/test/helpers.tsx`). Covered: API client (CSRF, errors), cover fallback, auth forms and redirects, Discover (filters, search notice, retry, pagination, mobile filters), book detail (shelf, rating, notes, duplicate error), recommendations cold start, library, preferences, evaluation page (inactive semantic notice, admin tools), layout/mobile menu, 404.

## End-to-end smoke (manual)

Run the API and `npm run dev`, then walk: register → set preferences → search → open a book → add to shelf → set progress/rating/note → “For you” → set goal → Evaluation. This flow was exercised once with headless Chromium against the real model during development.
