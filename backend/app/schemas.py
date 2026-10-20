from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

Status = Literal["want_to_read", "reading", "completed", "on_hold"]
Pacing = Literal["slow", "medium", "fast"]
TagStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth / users
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)

    @field_validator("display_name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("display name cannot be blank")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(Out):
    id: int
    email: str
    display_name: str
    is_admin: bool


class AuthOut(BaseModel):
    user: UserOut
    csrf_token: str


class PreferencesIO(BaseModel):
    genres: list[TagStr] = Field(default_factory=list, max_length=30)
    moods: list[TagStr] = Field(default_factory=list, max_length=30)
    tropes: list[TagStr] = Field(default_factory=list, max_length=30)
    avoid_content_warnings: list[TagStr] = Field(default_factory=list, max_length=30)
    pacing: Pacing | None = None


# --- books
class BookOut(Out):
    id: int
    slug: str
    title: str
    subtitle: str | None
    description: str | None
    first_publish_year: int | None
    page_count: int | None
    cover_url: str | None
    pacing: str | None
    authors: list[str]
    genres: list[str]
    moods: list[str]
    tropes: list[str]
    content_warnings: list[str]
    source: str
    has_embedding: bool | None = None


class RankedBook(BaseModel):
    book: BookOut
    score: float
    explanation: str
    factors: list[dict[str, Any]]


class Page(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class BrowseOut(BaseModel):
    items: list[BookOut]
    meta: Page


class SearchMeta(Page):
    mode_used: str
    semantic_available: bool
    notice: str | None = None
    books_without_embeddings: int = 0
    cold_start: bool = False


class SearchOut(BaseModel):
    items: list[RankedBook]
    meta: SearchMeta


class FacetItem(BaseModel):
    name: str
    count: int


class FacetsOut(BaseModel):
    genres: list[FacetItem]
    moods: list[FacetItem]
    tropes: list[FacetItem]
    content_warnings: list[FacetItem]
    pacing: list[FacetItem]
    year_min: int | None
    year_max: int | None


# --- library
class LibraryAddIn(BaseModel):
    book_id: int
    status: Status = "want_to_read"


class LibraryStatusIn(BaseModel):
    status: Status


class ProgressIn(BaseModel):
    current_page: int | None = Field(default=None, ge=0, le=100000)
    progress_percent: int | None = Field(default=None, ge=0, le=100)


class EntryOut(Out):
    id: int
    book: BookOut
    status: str
    progress_percent: int
    current_page: int | None
    started_at: date | None
    finished_at: date | None
    updated_at: datetime
    rating: int | None = None


class RatingIn(BaseModel):
    value: int = Field(ge=1, le=5)


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)

    @field_validator("body")
    @classmethod
    def _nb(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("note cannot be blank")
        return v


class NoteOut(Out):
    id: int
    book_id: int
    body: str
    created_at: datetime
    updated_at: datetime


class GoalIn(BaseModel):
    target_books: int = Field(ge=1, le=1000)


class GoalOut(BaseModel):
    year: int
    target_books: int | None
    completed: int


# --- admin / eval
class ImportIn(BaseModel):
    query: str = Field(min_length=2, max_length=200)
    limit: int = Field(default=10, ge=1, le=25)


class EvalRunIn(BaseModel):
    k: int = Field(default=5, ge=1, le=20)
