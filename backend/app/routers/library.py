from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response
from sqlalchemy import extract, func, select
from sqlalchemy.exc import IntegrityError

from app.deps import DB, CurrentUser
from app.errors import AppError, not_found
from app.models import Book, Note, Rating, ReadingEntry, ReadingGoal
from app.schemas import (
    EntryOut,
    GoalIn,
    GoalOut,
    LibraryAddIn,
    LibraryStatusIn,
    NoteIn,
    NoteOut,
    Page,
    ProgressIn,
    RatingIn,
    Status,
)
from app.serializers import book_out

router = APIRouter(tags=["library"])


def _entry_out(e: ReadingEntry, rating: int | None) -> EntryOut:
    return EntryOut(
        id=e.id,
        book=book_out(e.book),
        status=e.status,
        progress_percent=e.progress_percent,
        current_page=e.current_page,
        started_at=e.started_at,
        finished_at=e.finished_at,
        updated_at=e.updated_at,
        rating=rating,
    )


def _rating(db: DB, user_id: int, book_id: int) -> int | None:
    return db.scalar(select(Rating.value).where(Rating.user_id == user_id, Rating.book_id == book_id))


def _get_entry(db: DB, user_id: int, book_id: int) -> ReadingEntry:
    e = db.scalar(select(ReadingEntry).where(ReadingEntry.user_id == user_id, ReadingEntry.book_id == book_id))
    if e is None:
        raise not_found("Library entry")
    return e


def _apply_status(e: ReadingEntry, status: str, book: Book) -> None:
    today = date.today()
    prev = e.status
    e.status = status
    if status == "reading" and e.started_at is None:
        e.started_at = today
    if status == "completed":
        e.started_at = e.started_at or today
        e.finished_at = e.finished_at or today
        e.progress_percent = 100
        if book.page_count:
            e.current_page = book.page_count
    elif prev == "completed":
        e.finished_at = None
        if e.progress_percent == 100:
            e.progress_percent = 0
            e.current_page = None


@router.get("/library")
def list_library(
    db: DB,
    user: CurrentUser,
    status: Status | None = None,
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 24,
):
    cond = [ReadingEntry.user_id == user.id] + ([ReadingEntry.status == status] if status else [])
    total = db.scalar(select(func.count()).select_from(ReadingEntry).where(*cond)) or 0
    rows = (
        db.scalars(
            select(ReadingEntry)
            .where(*cond)
            .order_by(ReadingEntry.updated_at.desc(), ReadingEntry.id)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        .unique()
        .all()
    )
    ratings = dict(db.execute(select(Rating.book_id, Rating.value).where(Rating.user_id == user.id)).all())
    counts = dict(
        db.execute(
            select(ReadingEntry.status, func.count())
            .where(ReadingEntry.user_id == user.id)
            .group_by(ReadingEntry.status)
        ).all()
    )
    return {
        "items": [_entry_out(e, ratings.get(e.book_id)) for e in rows],
        "meta": Page(page=page, page_size=page_size, total=total, pages=max(1, -(-total // page_size))),
        "counts": {s: counts.get(s, 0) for s in ("want_to_read", "reading", "completed", "on_hold")},
    }


@router.post("/library", response_model=EntryOut, status_code=201)
def add_to_library(body: LibraryAddIn, db: DB, user: CurrentUser):
    book = db.get(Book, body.book_id)
    if book is None:
        raise not_found("Book")
    e = ReadingEntry(user_id=user.id, book_id=book.id, status=body.status)
    db.add(e)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "already_in_library", "This book is already on your shelf") from None
    _apply_status(e, body.status, book)
    db.commit()
    db.refresh(e)
    return _entry_out(e, _rating(db, user.id, book.id))


@router.get("/me/books/{book_id}")
def my_book_state(book_id: int, db: DB, user: CurrentUser):
    if db.get(Book, book_id) is None:
        raise not_found("Book")
    e = db.scalar(select(ReadingEntry).where(ReadingEntry.user_id == user.id, ReadingEntry.book_id == book_id))
    r = _rating(db, user.id, book_id)
    return {"entry": _entry_out(e, r) if e else None, "rating": r}


@router.put("/library/{book_id}/status", response_model=EntryOut)
def set_status(book_id: int, body: LibraryStatusIn, db: DB, user: CurrentUser):
    e = _get_entry(db, user.id, book_id)
    _apply_status(e, body.status, e.book)
    db.commit()
    return _entry_out(e, _rating(db, user.id, book_id))


@router.patch("/library/{book_id}/progress", response_model=EntryOut)
def set_progress(book_id: int, body: ProgressIn, db: DB, user: CurrentUser):
    if body.current_page is None and body.progress_percent is None:
        raise AppError(422, "validation_error", "Provide current_page or progress_percent")
    e = _get_entry(db, user.id, book_id)
    pages = e.book.page_count
    if body.current_page is not None:
        if pages and body.current_page > pages:
            raise AppError(422, "validation_error", f"current_page cannot exceed the book's {pages} pages")
        e.current_page = body.current_page
        if pages:
            e.progress_percent = round(100 * body.current_page / pages)
    if body.progress_percent is not None:
        e.progress_percent = body.progress_percent
        if pages:
            e.current_page = round(pages * body.progress_percent / 100)
    if e.progress_percent >= 100:
        _apply_status(e, "completed", e.book)
    elif e.status in ("want_to_read", "completed"):
        _apply_status(e, "reading", e.book)
    db.commit()
    return _entry_out(e, _rating(db, user.id, book_id))


@router.delete("/library/{book_id}", status_code=204)
def remove_from_library(book_id: int, db: DB, user: CurrentUser):
    e = _get_entry(db, user.id, book_id)
    db.delete(e)
    db.commit()
    return Response(status_code=204)


# --- ratings
@router.put("/books/{book_id}/rating")
def put_rating(book_id: int, body: RatingIn, db: DB, user: CurrentUser):
    if db.get(Book, book_id) is None:
        raise not_found("Book")
    r = db.scalar(select(Rating).where(Rating.user_id == user.id, Rating.book_id == book_id))
    if r is None:
        r = Rating(user_id=user.id, book_id=book_id, value=body.value)
        db.add(r)
    else:
        r.value = body.value
    db.commit()
    return {"book_id": book_id, "value": r.value}


@router.delete("/books/{book_id}/rating", status_code=204)
def delete_rating(book_id: int, db: DB, user: CurrentUser):
    r = db.scalar(select(Rating).where(Rating.user_id == user.id, Rating.book_id == book_id))
    if r is None:
        raise not_found("Rating")
    db.delete(r)
    db.commit()
    return Response(status_code=204)


# --- notes (private to the author; other users' notes read as not found)
@router.get("/books/{book_id}/notes", response_model=list[NoteOut])
def list_notes(book_id: int, db: DB, user: CurrentUser):
    return db.scalars(
        select(Note)
        .where(Note.user_id == user.id, Note.book_id == book_id)
        .order_by(Note.created_at.desc(), Note.id.desc())
    ).all()


@router.post("/books/{book_id}/notes", response_model=NoteOut, status_code=201)
def create_note(book_id: int, body: NoteIn, db: DB, user: CurrentUser):
    if db.get(Book, book_id) is None:
        raise not_found("Book")
    n = Note(user_id=user.id, book_id=book_id, body=body.body.strip())
    db.add(n)
    db.commit()
    return n


def _own_note(db: DB, user_id: int, note_id: int) -> Note:
    n = db.get(Note, note_id)
    if n is None or n.user_id != user_id:
        raise not_found("Note")
    return n


@router.put("/notes/{note_id}", response_model=NoteOut)
def update_note(note_id: int, body: NoteIn, db: DB, user: CurrentUser):
    n = _own_note(db, user.id, note_id)
    n.body = body.body.strip()
    db.commit()
    return n


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: int, db: DB, user: CurrentUser):
    db.delete(_own_note(db, user.id, note_id))
    db.commit()
    return Response(status_code=204)


# --- goals
def _goal_out(db: DB, user_id: int, year: int) -> GoalOut:
    g = db.scalar(select(ReadingGoal).where(ReadingGoal.user_id == user_id, ReadingGoal.year == year))
    done = (
        db.scalar(
            select(func.count())
            .select_from(ReadingEntry)
            .where(
                ReadingEntry.user_id == user_id,
                ReadingEntry.status == "completed",
                extract("year", ReadingEntry.finished_at) == year,
            )
        )
        or 0
    )
    return GoalOut(year=year, target_books=g.target_books if g else None, completed=done)


YearP = Annotated[int, Query(ge=1900, le=2200)]


@router.get("/goals", response_model=GoalOut)
def get_goal(db: DB, user: CurrentUser, year: YearP = date.today().year):
    return _goal_out(db, user.id, year)


@router.put("/goals", response_model=GoalOut)
def put_goal(body: GoalIn, db: DB, user: CurrentUser, year: YearP = date.today().year):
    g = db.scalar(select(ReadingGoal).where(ReadingGoal.user_id == user.id, ReadingGoal.year == year))
    if g is None:
        db.add(ReadingGoal(user_id=user.id, year=year, target_books=body.target_books))
    else:
        g.target_books = body.target_books
    db.commit()
    return _goal_out(db, user.id, year)
