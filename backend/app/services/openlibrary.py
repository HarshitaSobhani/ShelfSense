"""Open Library integration (https://openlibrary.org/dev/docs/api/search). No API key needed;
a descriptive User-Agent with contact info is requested by Open Library's usage policy."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.config import get_settings

log = logging.getLogger("shelfsense.openlibrary")
FIELDS = "key,title,author_name,author_key,first_publish_year,cover_i,subject,number_of_pages_median,language"


class ExternalServiceError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.message, self.status = message, status


def _client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    s = get_settings()
    return httpx.Client(
        base_url=s.openlibrary_base_url,
        timeout=s.openlibrary_timeout,
        headers={"User-Agent": f"ShelfSense/0.1 ({s.openlibrary_contact})"},
        transport=transport,
        follow_redirects=True,
    )


_BAD_SUBJECT = re.compile(r"[:/\d]|^(accessible book|protected daisy|in library|large type|reading level)", re.I)


def clean_subjects(subjects: list[str] | None, limit: int = 6) -> list[str]:
    out: list[str] = []
    for s in subjects or []:
        s = s.strip().lower()
        if 2 < len(s) <= 40 and not _BAD_SUBJECT.search(s) and s not in out:
            out.append(s)
        if len(out) >= limit:
            break
    return out


def parse_doc(doc: dict[str, Any]) -> dict[str, Any] | None:
    """Map a search.json doc to our book dict. Returns None if essential fields are missing."""
    title, key = doc.get("title"), doc.get("key")
    authors = doc.get("author_name") or []
    if not title or not key or not authors:
        return None
    ol_key = key.rsplit("/", 1)[-1]
    out: dict[str, Any] = {
        "title": title,
        "authors": authors[:4],
        "author_keys": (doc.get("author_key") or [])[:4],
        "open_library_key": ol_key,
        "genres": clean_subjects(doc.get("subject")),
    }
    if isinstance(doc.get("first_publish_year"), int):
        out["first_publish_year"] = doc["first_publish_year"]
    if isinstance(doc.get("number_of_pages_median"), int):
        out["page_count"] = doc["number_of_pages_median"]
    if doc.get("language"):
        out["language"] = doc["language"][0][:8]
    if doc.get("cover_i"):
        out["cover_url"] = f"{get_settings().openlibrary_covers_url}/b/id/{doc['cover_i']}-L.jpg"
    return out


def _get(client: httpx.Client, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        r = client.get(path, params=params)
    except httpx.HTTPError as e:
        raise ExternalServiceError(f"Open Library request failed: {type(e).__name__}") from e
    if r.status_code >= 400:
        raise ExternalServiceError(f"Open Library returned HTTP {r.status_code}", r.status_code)
    try:
        data = r.json()
    except ValueError as e:
        raise ExternalServiceError("Open Library returned invalid JSON") from e
    if not isinstance(data, dict):
        raise ExternalServiceError("Open Library returned an unexpected payload")
    return data


def search_works(query: str, limit: int, transport: httpx.BaseTransport | None = None) -> list[dict[str, Any]]:
    with _client(transport) as c:
        data = _get(c, "/search.json", {"q": query, "limit": limit, "fields": FIELDS})
    return [d for d in data.get("docs", []) if isinstance(d, dict)]


def fetch_work(ol_key: str, transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    with _client(transport) as c:
        return _get(c, f"/works/{ol_key}.json")


def work_description(work: dict[str, Any]) -> str | None:
    d = work.get("description")
    if isinstance(d, dict):
        d = d.get("value")
    return d.strip() if isinstance(d, str) and d.strip() else None
