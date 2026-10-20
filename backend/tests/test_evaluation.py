import pytest
from sqlalchemy import select

from app.models import EvaluationRun
from app.seed.loader import load_seed
from app.services.evaluation import load_judgments, metrics_for, run_evaluation
from tests.conftest import new_client


def test_metrics_known_values():
    m = metrics_for([10, 11, 12, 13, 14], {11, 14, 99}, k=5)
    assert m["recall"] == pytest.approx(2 / 3) and m["precision"] == pytest.approx(0.4) and m["mrr"] == 0.5
    # DCG = 1/log2(3) + 1/log2(6); IDCG over 3 relevant = 1 + 1/log2(3) + 1/log2(4)
    assert m["ndcg"] == pytest.approx((0.6309297536 + 0.3868528072) / (1 + 0.6309297536 + 0.5))
    assert metrics_for([1, 2], {1}, 2)["ndcg"] == 1.0
    assert metrics_for([1, 2], set(), 2)["recall"] == 0.0 and metrics_for([], {1}, 3)["mrr"] == 0.0


def test_judgments_reference_only_titles_in_seed_catalog(db):
    load_seed(db)
    from app.models import Book

    titles = {b.title for b in db.scalars(select(Book))}
    for q in load_judgments()["queries"]:
        assert set(q["relevant"]) <= titles, q


def test_seed_loader_is_idempotent(db):
    n = load_seed(db)
    load_seed(db)
    from app.models import Book

    assert db.query(Book).count() == n == 62


def test_run_without_embeddings_evaluates_keyword_only_and_says_so(db):
    load_seed(db)
    r = run_evaluation(db, k=5)
    assert list(r["modes"]) == ["keyword"] and {s["mode"] for s in r["skipped_modes"]} == {"semantic", "hybrid"}
    assert r["embedding_model"] is None and "not by independent" in r["caveat"]
    assert 0 <= r["modes"]["keyword"]["mean"]["ndcg"] <= 1
    assert db.scalar(select(EvaluationRun)) is not None


def test_run_with_embedder_covers_three_modes(db, embedder):
    from app.services.catalog import index_books

    load_seed(db)
    index_books(db)
    r = run_evaluation(db, k=3)
    assert list(r["modes"]) == ["keyword", "semantic", "hybrid"] and r["skipped_modes"] == []
    assert len(r["modes"]["semantic"]["queries"]) == len(load_judgments()["queries"])


def test_evaluation_endpoints_permissions(client, auth, db, monkeypatch):
    load_seed(db)
    assert client.post("/api/v1/evaluation/run", json={"k": 5}).status_code == 403
    r = client.get("/api/v1/evaluation/runs").json()
    assert r["runs"] == [] and r["judgments"]["query_count"] == 19
    monkeypatch.setenv("SHELFSENSE_ADMIN_EMAILS", "root@example.com")
    from app.config import get_settings

    get_settings.cache_clear()
    admin = new_client("root@example.com")
    out = admin.post("/api/v1/evaluation/run", json={"k": 5})
    assert out.status_code == 200 and "keyword" in out.json()["modes"]
    assert len(client.get("/api/v1/evaluation/runs").json()["runs"]) == 1
    assert admin.post("/api/v1/evaluation/run", json={"k": 0}).status_code == 422
    monkeypatch.delenv("SHELFSENSE_ADMIN_EMAILS")
    get_settings.cache_clear()
