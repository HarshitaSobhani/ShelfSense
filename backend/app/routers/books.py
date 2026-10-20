from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.deps import DB, CurrentUser
from app.errors import not_found
from app.models import Book, BookTag, Tag
from app.schemas import BookOut, BrowseOut, FacetItem, FacetsOut, Page, RankedBook, SearchMeta, SearchOut
from app.serializers import book_out
from app.services import discovery, vectorstore
from app.services.discovery import Hit, SearchResult
from app.services.filters import BookFilters, conditions

router = APIRouter(tags=["books"])

Csv = Annotated[list[str] | None, Query(max_length=20)]


def parse_filters(
    genre: Csv = None,
    mood: Csv = None,
    trope: Csv = None,
    avoid: Csv = None,
    pacing: Literal["slow", "medium", "fast"] | None = None,
    year_min: Annotated[int | None, Query(ge=-3000, le=3000)] = None,
    year_max: Annotated[int | None, Query(ge=-3000, le=3000)] = None,
) -> BookFilters:
    return BookFilters(genre or [], mood or [], trope or [], avoid or [], pacing, year_min, year_max)


def _page(total: int, page: int, size: int) -> Page:
    return Page(page=page, page_size=size, total=total, pages=max(1, -(-total // size)))


def _search_out(res: SearchResult, page: int, size: int) -> SearchOut:
    sl = res.hits[(page - 1) * size : page * size]
    base = _page(len(res.hits), page, size)
    return SearchOut(
        items=[_ranked(h) for h in sl],
        meta=SearchMeta(
            **base.model_dump(),
            mode_used=res.mode_used,
            semantic_available=res.semantic_available,
            notice=res.notice,
            books_without_embeddings=res.books_without_embeddings,
            cold_start=res.cold_start,
        ),
    )


def _ranked(h: Hit) -> RankedBook:
    return RankedBook(book=book_out(h.book), score=round(h.score, 4), explanation=h.explanation, factors=h.factors)


Filters = Annotated[BookFilters, Depends(parse_filters)]
PageQ = Annotated[int, Query(ge=1, le=1000)]
SizeQ = Annotated[int, Query(ge=1, le=50)]


@router.get("/books", response_model=BrowseOut)
def browse(
    db: DB,
    f: Filters,
    page: PageQ = 1,
    page_size: SizeQ = 12,
    sort: Literal["title", "year_desc", "year_asc", "recent"] = "title",
):
    conds = conditions(f)
    total = db.scalar(select(func.count()).select_from(Book).where(*conds)) or 0
    order = {
        "title": Book.title,
        "year_desc": Book.first_publish_year.desc().nulls_last(),
        "year_asc": Book.first_publish_year.asc().nulls_last(),
        "recent": Book.created_at.desc(),
    }[sort]
    rows = db.scalars(
        select(Book).where(*conds).order_by(order, Book.id).limit(page_size).offset((page - 1) * page_size)
    ).all()
    return BrowseOut(items=[book_out(b) for b in rows], meta=_page(total, page, page_size))


@router.get("/books/search", response_model=SearchOut)
def search_books(
    db: DB,
    f: Filters,
    q: Annotated[str, Query(min_length=2, max_length=300)],
    mode: Literal["auto", "hybrid", "semantic", "keyword"] = "auto",
    page: PageQ = 1,
    page_size: SizeQ = 12,
):
    return _search_out(discovery.search(db, q.strip(), f, mode=mode), page, page_size)


@router.get("/books/facets", response_model=FacetsOut)
def facets(db: DB):
    rows = db.execute(
        select(Tag.kind, Tag.name, func.count(BookTag.book_id))
        .join(BookTag, BookTag.tag_id == Tag.id)
        .group_by(Tag.kind, Tag.name)
        .order_by(func.count(BookTag.book_id).desc(), Tag.name)
    ).all()
    by: dict[str, list[FacetItem]] = {"genre": [], "mood": [], "trope": [], "content_warning": []}
    for kind, name, n in rows:
        by[kind].append(FacetItem(name=name, count=n))
    pace = db.execute(select(Book.pacing, func.count()).where(Book.pacing.is_not(None)).group_by(Book.pacing)).all()
    yr = db.execute(select(func.min(Book.first_publish_year), func.max(Book.first_publish_year))).one()
    return FacetsOut(
        genres=by["genre"],
        moods=by["mood"],
        tropes=by["trope"],
        content_warnings=by["content_warning"],
        pacing=[FacetItem(name=p, count=c) for p, c in pace],
        year_min=yr[0],
        year_max=yr[1],
    )


@router.get("/books/{book_id}", response_model=BookOut)
def book_detail(book_id: int, db: DB):
    b = db.get(Book, book_id)
    if b is None:
        raise not_found("Book")
    has = book_id in vectorstore.get_vectors(db, [book_id]) if vectorstore.backend(db) else False
    return book_out(b, has)


@router.get("/books/{book_id}/similar", response_model=SearchOut)
def similar_books(book_id: int, db: DB, limit: Annotated[int, Query(ge=1, le=24)] = 8):
    b = db.get(Book, book_id)
    if b is None:
        raise not_found("Book")
    return _search_out(discovery.similar(db, b, limit), 1, limit)


@router.get("/recommendations", response_model=SearchOut)
def recommendations(
    db: DB,
    user: CurrentUser,
    f: Filters,
    exclude_read: bool = True,
    page: PageQ = 1,
    page_size: SizeQ = 12,
):
    res = discovery.recommend(db, user.id, f, exclude_read=exclude_read, limit=100)
    return _search_out(res, page, page_size)
