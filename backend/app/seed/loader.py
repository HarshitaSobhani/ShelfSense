import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.services.catalog import upsert_book

CATALOG = Path(__file__).with_name("catalog.json")


def load_seed(db: Session, path: Path = CATALOG) -> int:
    rows = json.loads(path.read_text(encoding="utf-8"))
    for row in rows:
        upsert_book(db, row, source="seed")
    db.commit()
    return len(rows)
