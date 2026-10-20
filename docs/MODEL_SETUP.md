# Embedding model setup

**Model:** `sentence-transformers/all-MiniLM-L6-v2`, 384 dimensions, ~90 MB, CPU-friendly, Apache-2.0 licensed on Hugging Face.
Configured by `SHELFSENSE_EMBEDDING_MODEL`, `SHELFSENSE_EMBEDDING_MODEL_REVISION` and `SHELFSENSE_EMBEDDING_DIM`.

## First-time setup

```bash
pip install -e "backend[embeddings]" --extra-index-url https://download.pytorch.org/whl/cpu   # CPU-only torch
cd backend
python -m app.cli download-model     # loads (and caches) the model; exit code 1 + reason if it cannot
python -m app.cli rebuild-index      # embeds every book that is missing a vector or whose text/model changed
```

`GET /api/v1/health` → `semantic_search.active` is `true` only when the model loads **and** at least one vector is stored.
Until then the UI shows “Not active” and search uses keyword + tag matching. `mode=semantic` responds `503 semantic_unavailable`.

## When the model cannot be downloaded

1. Download on a machine with access: `python -c "from sentence_transformers import SentenceTransformer as S; S('sentence-transformers/all-MiniLM-L6-v2')"`.
2. Copy the cache directory (`~/.cache/huggingface`, or `$HF_HOME`) to the target host, set `HF_HOME` to it and `HF_HUB_OFFLINE=1`.
   Alternatively set `SHELFSENSE_EMBEDDING_MODEL=/path/to/local/model-dir`.
3. Or run without semantic search: `SHELFSENSE_EMBEDDING_PROVIDER=none` (keyword/metadata fallback; nothing claims otherwise).

## Versioning and rebuilding

Each row in `book_embeddings` stores `model_name`, `model_revision`, `schema_version`, `dim` and a `content_hash`
(`sha256(schema_version | model | document text)`).

- **Book text/tags changed** (e.g. after an Open Library refresh): `python -m app.cli rebuild-index` re-embeds only changed books.
- **Changed the document template** (`services/normalize.py: build_document`): bump `SHELFSENSE_EMBEDDING_SCHEMA_VERSION` and run `rebuild-index`.
- **Changed the model** (same dimension): update `SHELFSENSE_EMBEDDING_MODEL` (and pin `…_REVISION` to a commit hash), run `rebuild-index --force`. `/health` reports `stale_embeddings` until you do.
- **Changed the dimension**: add an Alembic migration that alters `book_embeddings.embedding` to `vector(<new dim>)` (and rebuilds the HNSW index), update `SHELFSENSE_EMBEDDING_DIM`, then `rebuild-index --force`.
- Admins can also trigger a rebuild from the Evaluation page or `POST /api/v1/admin/embeddings/rebuild`.

Re-run `python -m app.cli evaluate` after any model or weight change and compare with the previous run on `/evaluation`.

## No pgvector?

If `CREATE EXTENSION vector` fails during migration, the column is created as `double precision[]` and cosine similarity is computed in numpy
(`services/vectorstore.py`). This is correct but O(n) per query; use pgvector for catalogs beyond a few thousand books.
