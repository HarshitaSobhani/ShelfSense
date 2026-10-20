"""Metadata normalization and embedding-document construction."""

import hashlib
import re
import unicodedata

_ws = re.compile(r"\s+")


def clean_text(s: str | None) -> str | None:
    if s is None:
        return None
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = _ws.sub(" ", s).strip()
    return s or None


def normalize_tag(s: str) -> str:
    return _ws.sub(" ", unicodedata.normalize("NFKC", s).strip().lower())


def normalize_tags(values: list[str] | None, limit: int = 30) -> list[str]:
    seen: dict[str, None] = {}
    for v in values or []:
        n = normalize_tag(v)
        if n and len(n) <= 80:
            seen.setdefault(n, None)
    return list(seen)[:limit]


def normalize_author(name: str) -> str:
    base = unicodedata.normalize("NFKD", name)
    base = "".join(c for c in base if not unicodedata.combining(c))
    return _ws.sub(" ", re.sub(r"[^\w\s]", " ", base.lower())).strip()


def slugify(title: str, year: int | None = None) -> str:
    base = unicodedata.normalize("NFKD", title)
    base = "".join(c for c in base if not unicodedata.combining(c)).lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:150] or "book"
    return f"{base}-{year}" if year else base


def build_document(
    title: str,
    authors: list[str],
    description: str | None,
    genres: list[str],
    moods: list[str],
    tropes: list[str],
    pacing: str | None,
) -> str:
    """Text embedded for a book. Only fields that exist are included; the document is never padded
    with invented text. A book with no description and no tags embeds title/author only."""
    parts = [title]
    if authors:
        parts.append("by " + ", ".join(authors))
    if genres:
        parts.append("Genres: " + ", ".join(genres))
    if moods:
        parts.append("Mood: " + ", ".join(moods))
    if tropes:
        parts.append("Themes and tropes: " + ", ".join(tropes))
    if pacing:
        parts.append(f"Pacing: {pacing}")
    if description:
        parts.append(description)
    return ". ".join(parts)


def content_hash(document: str, model: str, schema_version: int) -> str:
    return hashlib.sha256(f"{schema_version}|{model}|{document}".encode()).hexdigest()
