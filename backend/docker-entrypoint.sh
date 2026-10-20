#!/bin/sh
set -e
echo "Applying migrations..."
alembic upgrade head
if [ "${SHELFSENSE_SEED_ON_START:-true}" = "true" ]; then
  echo "Seeding catalog (idempotent) and indexing embeddings if a model is available..."
  python -m app.cli seed || echo "Seed/index step reported a problem; the API will start with keyword search only."
fi
exec "$@"
