import json

import pytest

from app import cli
from app.config import get_settings
from app.models import User
from app.security import hash_password
from app.services import embeddings


@pytest.fixture
def broken_model(monkeypatch):
    """A model that cannot be loaded (offline, nonexistent): the 'download failed' scenario."""
    monkeypatch.setenv("SHELFSENSE_EMBEDDING_PROVIDER", "sentence-transformers")
    monkeypatch.setenv("SHELFSENSE_EMBEDDING_MODEL", "does-not-exist/nope-model")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    get_settings.cache_clear()
    embeddings.reset_embedder()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()
    embeddings.reset_embedder()


def test_unloadable_model_reports_reason_and_setup(broken_model):
    assert embeddings.get_embedder() is None
    st = embeddings.embedder_status()
    assert st.available is False and "could not load model" in st.reason and "MODEL_SETUP" in st.setup


def test_health_and_search_degrade_honestly_with_unloadable_model(broken_model, client, small_catalog_no_embeddings):
    h = client.get("/api/v1/health").json()["semantic_search"]
    assert h["active"] is False and h["model_loaded"] is False and "does-not-exist/nope-model" in h["reason"]
    r = client.get("/api/v1/books/search", params={"q": "haunted manor"})
    assert r.status_code == 200 and r.json()["meta"]["mode_used"] == "keyword"


def test_provider_none_is_reported(client):
    st = embeddings.embedder_status()
    assert st.available is False and "disabled" in st.reason


def test_cli_status_and_download_model_exit_codes(capsys, broken_model):
    assert cli.main(["status"]) == 0
    assert json.loads(capsys.readouterr().out)["available"] is False
    assert cli.main(["download-model"]) == 1


def test_cli_seed_make_admin_and_rebuild(db, capsys, embedder):
    assert cli.main(["seed"]) == 0
    out = capsys.readouterr().out
    assert "seeded 62 books" in out and '"indexed": 62' in out
    assert cli.main(["rebuild-index"]) == 0
    assert cli.main(["make-admin", "nobody@example.com"]) == 1
    db.add(User(email="a@example.com", password_hash=hash_password("x" * 12), display_name="A"))
    db.commit()
    assert cli.main(["make-admin", "A@example.com"]) == 0
    db.expire_all()
    assert db.query(User).one().is_admin is True


def test_cli_rebuild_index_fails_without_model(db, capsys):
    assert cli.main(["rebuild-index"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "unavailable"


def test_production_refuses_placeholder_secret(monkeypatch):
    monkeypatch.setenv("SHELFSENSE_ENVIRONMENT", "production")
    monkeypatch.setenv("SHELFSENSE_SECRET_KEY", "replace-with-a-long-random-string")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError):
            get_settings()
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
