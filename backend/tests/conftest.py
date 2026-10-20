import os
import re

TEST_URL = os.environ.get(
    "SHELFSENSE_TEST_DATABASE_URL",
    "postgresql+psycopg://shelfsense:shelfsense@localhost:5432/shelfsense_test",
)
os.environ["SHELFSENSE_DATABASE_URL"] = TEST_URL
os.environ["SHELFSENSE_ENVIRONMENT"] = "test"
os.environ["SHELFSENSE_SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["SHELFSENSE_RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["SHELFSENSE_AUTH_RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["SHELFSENSE_EMBEDDING_PROVIDER"] = "none"  # tests never download models; they inject embedders

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import Base, reset_engine, session_factory  # noqa: E402
from app.services.catalog import index_books, upsert_book  # noqa: E402
from app.services.embeddings import reset_embedder, set_embedder_override  # noqa: E402

DIM = 384
CONCEPTS = {
    "cozy": ["cozy", "warm", "gentle", "tea", "friendship", "comfort"],
    "dark": ["dark", "murder", "haunted", "grim", "dread", "killer"],
    "space": ["space", "starship", "planet", "astronaut", "alien", "galaxy"],
    "romance": ["romance", "love", "lovers", "kiss", "courtship"],
    "magic": ["magic", "wizard", "spell", "dragon", "sorcery"],
    "history": ["history", "empire", "war", "medieval", "century"],
}


class ControlledEmbedder:
    """Test-only embedder: each concept owns one axis; a text's vector is the normalised count of
    concept keywords it contains. It makes similarity fully predictable and is NOT a language model."""

    name = "test/controlled-concepts"
    revision = "test"
    dim = DIM

    def embed(self, texts):
        out = np.zeros((len(texts), DIM), dtype=np.float32)
        for i, t in enumerate(texts):
            words = re.findall(r"[a-z']+", t.lower())
            for j, kws in enumerate(CONCEPTS.values()):
                out[i, j] = sum(words.count(k) for k in kws)
            if not out[i].any():
                out[i, DIM - 1] = 1.0  # "unknown" axis so zero vectors never occur
            out[i] /= np.linalg.norm(out[i])
        return out


@pytest.fixture(scope="session", autouse=True)
def _migrated():
    reset_engine()
    get_settings.cache_clear()
    eng = session_factory()().get_bind()
    with eng.begin() as c:
        c.execute(text("drop schema public cascade; create schema public"))
    command.upgrade(Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini")), "head")
    yield


@pytest.fixture(autouse=True)
def _clean():
    set_embedder_override(None)
    reset_embedder()
    yield
    with session_factory()() as db:
        names = ", ".join(t.name for t in Base.metadata.sorted_tables)
        db.execute(text(f"truncate {names} restart identity cascade"))
        db.commit()
    set_embedder_override(None)


@pytest.fixture
def db():
    with session_factory()() as s:
        yield s


@pytest.fixture
def client():
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def embedder():
    e = ControlledEmbedder()
    set_embedder_override(e)
    return e


BOOKS = [
    dict(
        title="Teacup Mornings",
        authors=["Ada Quill"],
        first_publish_year=2001,
        genres=["cozy mystery"],
        moods=["cozy"],
        tropes=["small town"],
        pacing="slow",
        description="A warm, gentle story of friendship and tea in a village.",
    ),
    dict(
        title="Ashes of the Manor",
        authors=["Bram Holt"],
        first_publish_year=1995,
        genres=["horror"],
        moods=["dark"],
        tropes=["haunted house"],
        pacing="medium",
        content_warnings=["violence"],
        description="A haunted manor and a grim killer bring dread to a family.",
    ),
    dict(
        title="Starship Lullaby",
        authors=["Cora Vance"],
        first_publish_year=2015,
        genres=["science fiction"],
        moods=["hopeful"],
        tropes=["found family"],
        pacing="fast",
        description="An astronaut and an alien share a starship crossing the galaxy.",
    ),
    dict(
        title="Kisses in the Mist",
        authors=["Dara Lund"],
        first_publish_year=2010,
        genres=["romance"],
        moods=["cozy"],
        tropes=["slow burn"],
        pacing="medium",
        description="A slow courtship and love between two neighbours; warm comfort.",
    ),
    dict(
        title="The Dragon's Spell",
        authors=["Ada Quill"],
        first_publish_year=1988,
        genres=["fantasy"],
        moods=["adventurous"],
        tropes=["quest"],
        pacing="medium",
        description="A wizard and a dragon use sorcery and magic on a long quest.",
    ),
    dict(
        title="Iron Empire",
        authors=["Eli Marsh"],
        first_publish_year=1975,
        genres=["historical fiction"],
        moods=["sombre"],
        tropes=["court intrigue"],
        pacing="slow",
        content_warnings=["war violence"],
        description="A medieval empire falls across a century of war and history.",
    ),
    dict(
        title="Nameless Volume",
        authors=["Fay Stone"],
        first_publish_year=None,
        genres=["fantasy"],
        moods=[],
        tropes=[],
        pacing=None,
        description=None,
    ),
]


@pytest.fixture
def small_catalog(db, embedder):
    ids = {}
    for b in BOOKS:
        ids[b["title"]] = upsert_book(db, dict(b)).id
    db.commit()
    index_books(db)
    return ids


@pytest.fixture
def small_catalog_no_embeddings(db):
    ids = {}
    for b in BOOKS:
        ids[b["title"]] = upsert_book(db, dict(b)).id
    db.commit()
    return ids


def register(client, email="reader@example.com", password="correct horse battery", name="Reader"):
    r = client.post("/api/v1/auth/register", json={"email": email, "password": password, "display_name": name})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def auth(client):
    data = register(client)
    client.headers["X-CSRF-Token"] = data["csrf_token"]
    return data


def new_client(email: str):
    """Independent logged-in client (separate cookie jar) for authorization tests."""
    from app.main import create_app

    c = TestClient(create_app())
    d = register(c, email=email)
    c.headers["X-CSRF-Token"] = d["csrf_token"]
    return c
