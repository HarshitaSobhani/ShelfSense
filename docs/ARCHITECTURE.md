# Architecture

```
React SPA ──/api/v1──▶ FastAPI ──▶ PostgreSQL (+pgvector)
                         │
                         ├─ services/discovery.py   retrieval + ranking glue
                         ├─ services/ranking.py     pure scoring (unit-tested on small datasets)
                         ├─ services/embeddings.py  model loading, explicit availability status
                         ├─ services/vectorstore.py pgvector or float8[] storage and search
                         ├─ services/catalog.py     upsert books, (re)build embeddings
                         ├─ services/openlibrary.py external metadata client
                         └─ services/evaluation.py  Recall/Precision/MRR/nDCG harness
```

## Data model (Alembic migration `0001`)

`users`, `authors`, `books`, `book_authors` (ordered), `tags` (kind: genre | mood | trope | content_warning) + `book_tags`,
`reading_entries` (unique `(user_id, book_id)`; status, progress %, page, started/finished dates), `ratings` (unique per user/book, 1–5),
`notes` (private), `reading_goals` (unique per user/year), `user_preferences`, `book_embeddings` (model name, revision, schema version,
dimension, content hash, vector) and `evaluation_runs`.

Indexes: GIN on the generated `books.search_tsv`, HNSW (`vector_cosine_ops`) on the embedding, composite indexes for shelf and tag lookups.
Constraints enforce status/pacing/rating/progress ranges and prevent duplicate shelf entries.

## Retrieval and ranking

1. **Normalise** (`services/normalize.py`): strip HTML/whitespace, lower-case and de-duplicate tags, normalise author names, slugs.
2. **Document** for embedding: `Title. by Authors. Genres: … Mood: … Themes and tropes: … Pacing: … Description`. Only fields that exist are included; nothing is invented. A book with no description still embeds from title/author/tags.
3. **Embed** with the configured model (normalised vectors). `content_hash = sha256(schema_version | model | document)`; the index only recomputes books whose hash changed.
4. **Filter** in SQL (genre/mood/trope ANY-within-kind and AND-across-kinds, pacing, year range, content-warning exclusion, explicit id exclusion).
5. **Search**: embed the query, take candidates with cosine ≥ `MIN_SEMANTIC_SCORE` (default 0.15), score = `(1-w)·cosine + w·lexical` (`w = HYBRID_LEXICAL_WEIGHT`, default 0.05) `+ 0.5` if a title/author contains the query. Hits scoring below `SEARCH_RELATIVE_CUTOFF` (0.5) × best are dropped so weak matches don't pad the list. A book with no stored vector is scored on its lexical factors only (weights renormalise) rather than being treated as dissimilar; the API reports how many books lack vectors.
6. **Recommend**: taste vector = weighted sum of the embeddings of books the user rated/saved (weights in `discovery.RATING_WEIGHT`/`SHELF_WEIGHT`), nearest neighbours among non-excluded books, then re-rank with explicit and implicit tag affinities (genre 0.12, mood 0.12, trope 0.10, pacing 0.04 against semantic 0.55 before renormalisation) and a small same-author diversity penalty. Without a usable taste vector the method degrades to `metadata_only` and says so. With no signals at all it returns `cold_start` and an empty list.
7. **Explain**: each hit returns `factors[]` (`factor`, `weight`, `value`, `contribution`, `evidence`) and a sentence generated from those factors and stored tags.

The weights are hand-set defaults, not learned. Change them in `services/ranking.py` / settings and re-run `python -m app.cli evaluate`.

## Security model

- Passwords: Argon2id via `pwdlib`; unknown-email logins perform a dummy hash to blunt timing enumeration; identical error for either failure.
- Sessions: signed JWT (HS256) in an `httpOnly`, `SameSite=Lax` cookie (`Secure` when `SHELFSENSE_COOKIE_SECURE=true`). A per-session CSRF token is also issued in a readable cookie and must be echoed in `X-CSRF-Token` for cookie-authenticated mutations. `Authorization: Bearer` requests need no CSRF header.
- Authorization: every library/rating/note/goal query is scoped by `user_id`; other users' notes and entries read as `404`. Admin endpoints require `is_admin`.
- Limits: 64 KiB body limit (by `Content-Length`; enforce at the proxy as well), in-process sliding-window rate limits (240 req/min per IP, 20 auth requests/min per IP), page-size caps, query-length caps.
- SQL: all queries are parameterised; LIKE patterns are escaped; tsquery input is reduced to `[a-z0-9]` tokens.
- Secrets: `SHELFSENSE_SECRET_KEY` is mandatory in production (startup fails on the dev default).
