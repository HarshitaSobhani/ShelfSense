from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

READING_STATUSES = ("want_to_read", "reading", "completed", "on_hold")
PACING = ("slow", "medium", "fast")
TAG_KINDS = ("genre", "mood", "trope", "content_warning")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(80))
    is_admin: Mapped[bool] = mapped_column(default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Author(Base):
    __tablename__ = "authors"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True)
    open_library_key: Mapped[str | None] = mapped_column(String(32), unique=True)


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("kind", "name"),
        CheckConstraint("kind in ('genre','mood','trope','content_warning')", name="tag_kind"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(80))


class BookTag(Base):
    __tablename__ = "book_tags"
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
    __table_args__ = (Index("ix_book_tags_tag", "tag_id", "book_id"),)


class BookAuthor(Base):
    __tablename__ = "book_authors"
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("authors.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(default=0)
    __table_args__ = (Index("ix_book_authors_author", "author_id"),)


class Book(Base):
    __tablename__ = "books"
    __table_args__ = (
        CheckConstraint("pacing is null or pacing in ('slow','medium','fast')", name="book_pacing"),
        Index("ix_books_search_tsv", "search_tsv", postgresql_using="gin"),
        Index("ix_books_year", "first_publish_year"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True)
    title: Mapped[str] = mapped_column(String(500))
    subtitle: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    first_publish_year: Mapped[int | None] = mapped_column(Integer)
    page_count: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str | None] = mapped_column(String(8))
    cover_url: Mapped[str | None] = mapped_column(String(500))
    pacing: Mapped[str | None] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(String(20), default="seed")  # seed | openlibrary
    open_library_key: Mapped[str | None] = mapped_column(String(32), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    search_tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(title,'') || ' ' || coalesce(subtitle,'') || ' ' "
            "|| coalesce(description,''))",
            persisted=True,
        ),
    )

    authors: Mapped[list[Author]] = relationship(
        secondary="book_authors", order_by="BookAuthor.position", viewonly=True, lazy="selectin"
    )
    tags: Mapped[list[Tag]] = relationship(secondary="book_tags", lazy="selectin", viewonly=True)

    def tag_names(self, kind: str) -> list[str]:
        return sorted(t.name for t in self.tags if t.kind == kind)


class BookEmbedding(Base):
    """Metadata for the stored vector. The `embedding` column itself is managed in SQL
    (pgvector `vector(dim)` when available, otherwise `double precision[]`)."""

    __tablename__ = "book_embeddings"
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), primary_key=True)
    model_name: Mapped[str] = mapped_column(String(200))
    model_revision: Mapped[str] = mapped_column(String(100))
    schema_version: Mapped[int] = mapped_column(Integer)
    dim: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReadingEntry(Base):
    __tablename__ = "reading_entries"
    __table_args__ = (
        UniqueConstraint("user_id", "book_id", name="uq_reading_user_book"),
        CheckConstraint("status in ('want_to_read','reading','completed','on_hold')", name="reading_status"),
        CheckConstraint("progress_percent between 0 and 100", name="reading_progress_range"),
        Index("ix_reading_user_status", "user_id", "status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20))
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    current_page: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[date | None] = mapped_column(Date)
    finished_at: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    book: Mapped[Book] = relationship(lazy="joined")


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (
        UniqueConstraint("user_id", "book_id", name="uq_rating_user_book"),
        CheckConstraint("value between 1 and 5", name="rating_range"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"))
    value: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (Index("ix_notes_user_book", "user_id", "book_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ReadingGoal(Base):
    __tablename__ = "reading_goals"
    __table_args__ = (
        UniqueConstraint("user_id", "year"),
        CheckConstraint("target_books between 1 and 1000", name="goal_range"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    year: Mapped[int] = mapped_column(Integer)
    target_books: Mapped[int] = mapped_column(Integer)


class UserPreference(Base):
    __tablename__ = "user_preferences"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    genres: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    moods: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    tropes: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    avoid_content_warnings: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    pacing: Mapped[str | None] = mapped_column(String(10))


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    k: Mapped[int] = mapped_column(Integer)
    catalog_size: Mapped[int] = mapped_column(Integer)
    embedding_model: Mapped[str | None] = mapped_column(String(200))
    judgments_version: Mapped[str] = mapped_column(String(50))
    results: Mapped[dict[str, Any]] = mapped_column(JSONB)
