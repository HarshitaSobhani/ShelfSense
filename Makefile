.PHONY: venv db migrate seed api web test lint typecheck build check eval docs
PY=.venv/bin/python

venv:
	python3 -m venv .venv && .venv/bin/pip install -e "backend[embeddings,dev]" --extra-index-url https://download.pytorch.org/whl/cpu
	cd frontend && npm ci

db:
	docker compose up -d db

migrate:
	cd backend && ../.venv/bin/alembic upgrade head

seed:
	cd backend && ../$(PY) -m app.cli seed

api:
	cd backend && ../.venv/bin/uvicorn app.main:app --reload --port 8000

web:
	cd frontend && npm run dev

test:
	cd backend && ../$(PY) -m pytest
	cd frontend && npm test

lint:
	cd backend && ../.venv/bin/ruff check . && ../.venv/bin/ruff format --check .
	cd frontend && npm run lint

typecheck:
	cd backend && ../.venv/bin/mypy app
	cd frontend && npm run typecheck

build:
	cd frontend && npm run build

check: lint typecheck test build

eval:
	cd backend && ../$(PY) -m app.cli evaluate

docs:
	cd backend && ../$(PY) -c "import json; from app.main import app; print(json.dumps(app.openapi(), indent=1))" > ../docs/openapi.json
