from app.models import Book
from app.schemas import BookOut


def book_out(b: Book, has_embedding: bool | None = None) -> BookOut:
    return BookOut(
        id=b.id,
        slug=b.slug,
        title=b.title,
        subtitle=b.subtitle,
        description=b.description,
        first_publish_year=b.first_publish_year,
        page_count=b.page_count,
        cover_url=b.cover_url,
        pacing=b.pacing,
        authors=[a.name for a in b.authors],
        genres=b.tag_names("genre"),
        moods=b.tag_names("mood"),
        tropes=b.tag_names("trope"),
        content_warnings=b.tag_names("content_warning"),
        source=b.source,
        has_embedding=has_embedding,
    )
