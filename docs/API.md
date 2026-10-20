# API

Base path `/api/v1`. Interactive docs: `/api/v1/docs`. Generated schema: [openapi.json](openapi.json) (`make docs`).

## Conventions

- JSON in/out. Auth: session cookie (browser) or `Authorization: Bearer <jwt>`.
- Cookie-authenticated `POST/PUT/PATCH/DELETE` must send `X-CSRF-Token` (value returned by login/register and in the `shelfsense_csrf` cookie).
- Pagination: `page` (≥1), `page_size` (default 12, max 50; library max 100). Responses include `meta: {page, page_size, total, pages}`.
- Errors always have this shape:

```json
{"error": {"code": "validation_error", "message": "Request validation failed",
           "details": [{"field": "password", "message": "String should have at least 10 characters"}],
           "request_id": "a1b2c3d4e5f60718"}}
```

Codes: `validation_error` 422, `unauthorized` 401, `invalid_credentials` 401, `csrf_failed` 403, `forbidden` 403, `not_found` 404,
`email_taken` 409, `already_in_library` 409, `not_refreshable` 409, `payload_too_large` 413, `rate_limited` 429,
`semantic_unavailable` 503, `external_service_unavailable` 502, `internal_error` 500.

## Endpoints

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/health` | – | DB, vector backend, **semantic-search status** (model loaded, indexed count, stale embeddings, setup hint) |
| POST | `/auth/register` | – | `{email, password(10-128), display_name}` → `{user, csrf_token}` and cookies |
| POST | `/auth/login` | – | `{email, password}` |
| POST | `/auth/logout` | – | clears cookies |
| GET | `/auth/me` | user | current user |
| GET/PUT | `/me/preferences` | user | `{genres, moods, tropes, avoid_content_warnings, pacing}` |
| GET | `/books` | – | browse; filters below; `sort=title\|year_desc\|year_asc\|recent` |
| GET | `/books/search` | – | `q` (2–300 chars), `mode=auto\|hybrid\|semantic\|keyword`, filters; returns ranked hits with `explanation` and `factors` |
| GET | `/books/facets` | – | tags with counts, pacing counts, year range |
| GET | `/books/{id}` | – | detail (`has_embedding`) |
| GET | `/books/{id}/similar` | – | `limit` ≤ 24; `meta.mode_used` is `embedding` or `metadata_fallback` |
| GET | `/recommendations` | user | `exclude_read=true`, filters, pagination; `meta.mode_used`: `embedding+metadata`, `metadata_only`, `cold_start` |
| GET/POST | `/library` | user | list (`status`, pagination, `counts`) / add `{book_id, status}` (409 if present) |
| PUT | `/library/{book_id}/status` | user | `{status}` (`want_to_read, reading, completed, on_hold`) |
| PATCH | `/library/{book_id}/progress` | user | `{current_page}` and/or `{progress_percent}`; 100% completes the book |
| DELETE | `/library/{book_id}` | user | remove from shelf |
| GET | `/me/books/{id}` | user | `{entry, rating}` for the detail page |
| PUT/DELETE | `/books/{id}/rating` | user | `{value: 1-5}` |
| GET/POST | `/books/{id}/notes` | user | private notes |
| PUT/DELETE | `/notes/{note_id}` | user | owner only (others get 404) |
| GET/PUT | `/goals?year=` | user | `{target_books}`; response includes completed count for the year |
| POST | `/admin/import/openlibrary` | admin | `{query, limit≤25}` → import + index; per-book description failures come back as `warnings` |
| POST | `/admin/books/{id}/refresh` | admin | refetch an Open Library book |
| POST | `/admin/embeddings/rebuild` | admin | `{force}` |
| GET | `/evaluation/runs` | user | last 10 stored runs + judgments metadata |
| POST | `/evaluation/run` | admin | `{k}` run and store an evaluation |

Filter query parameters (repeatable where noted): `genre*`, `mood*`, `trope*`, `avoid*` (hide books with these content warnings),
`pacing=slow|medium|fast`, `year_min`, `year_max`. Within one kind values are OR-ed; across kinds they are AND-ed.

## Example

```bash
curl -s 'http://localhost:8000/api/v1/books/search?q=a+cozy+adventure+with+found+family&page_size=3' | jq '.meta, .items[0].explanation'
```
