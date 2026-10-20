from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import ColumnElement, and_, exists, select

from app.models import Book, BookTag, Tag


@dataclass
class BookFilters:
    genres: list[str] = field(default_factory=list)
    moods: list[str] = field(default_factory=list)
    tropes: list[str] = field(default_factory=list)
    exclude_content_warnings: list[str] = field(default_factory=list)
    pacing: str | None = None
    year_min: int | None = None
    year_max: int | None = None
    exclude_ids: set[int] = field(default_factory=set)


def _has_tag(kind: str, names: list[str]) -> ColumnElement[bool]:
    return exists(
        select(1)
        .select_from(BookTag.__table__.join(Tag.__table__, Tag.id == BookTag.tag_id))
        .where(BookTag.book_id == Book.id, Tag.kind == kind, Tag.name.in_(names))
    )


def conditions(f: BookFilters) -> list[ColumnElement[bool]]:
    """Cross-kind AND, within-kind ANY. Content-warning exclusion removes any book carrying a listed warning."""
    c: list[ColumnElement[bool]] = []
    for kind, names in (("genre", f.genres), ("mood", f.moods), ("trope", f.tropes)):
        if names:
            c.append(_has_tag(kind, [n.strip().lower() for n in names]))
    if f.exclude_content_warnings:
        c.append(~_has_tag("content_warning", [n.strip().lower() for n in f.exclude_content_warnings]))
    if f.pacing:
        c.append(Book.pacing == f.pacing)
    if f.year_min is not None:
        c.append(and_(Book.first_publish_year.is_not(None), Book.first_publish_year >= f.year_min))
    if f.year_max is not None:
        c.append(and_(Book.first_publish_year.is_not(None), Book.first_publish_year <= f.year_max))
    if f.exclude_ids:
        c.append(Book.id.not_in(f.exclude_ids))
    return c
