"""
extract_text.py
Extract text per chapter from a PDF using pdfplumber and persist the results
to the database.

Chapter detection heuristic: a line is treated as a chapter heading when it
starts with "BAB" (case-insensitive) or consists entirely of uppercase text
that is short enough to be a title (≤ 80 characters).

Usage:
    python -m kupas.processor.extract_text
    python -m kupas.processor.extract_text --slug some-book-slug
"""

import argparse
import asyncio
import gc
import logging
import os
import re
from pathlib import Path

import pdfplumber
from dotenv import load_dotenv
from sqlalchemy import ForeignKey, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/kupas")

engine = create_async_engine(DATABASE_URL, echo=False)

PAGE_BATCH_SIZE = int(os.getenv("PDF_PAGE_BATCH_SIZE", "20"))

# Regex that matches common chapter headings such as:
#   "BAB 1", "BAB I", "BAB 1 PENDAHULUAN", "CHAPTER 1 …"
_CHAPTER_RE = re.compile(
    r"^(BAB\s+[\dIVXivx]+|CHAPTER\s+[\dIVXivx]+)",
    re.IGNORECASE,
)


class Base(DeclarativeBase):
    pass


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(unique=True, index=True)
    title: Mapped[str | None]
    pdf_path: Mapped[str | None]
    chapters: Mapped[list["Chapter"]] = relationship(
        "Chapter", back_populates="book", cascade="all, delete-orphan"
    )


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), index=True)
    chapter_number: Mapped[int]
    title: Mapped[str | None]
    content: Mapped[str | None] = mapped_column(Text)

    book: Mapped["Book"] = relationship("Book", back_populates="chapters")


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _is_chapter_heading(line: str) -> bool:
    """Return True if the line looks like a chapter heading."""
    stripped = line.strip()
    if not stripped:
        return False
    if _CHAPTER_RE.match(stripped):
        return True
    # Short ALL-CAPS line that looks like a title:
    # - more than 4 chars to skip single acronyms (e.g. "PDF", "ISBN")
    # - at most 80 chars so that body sentences in all-caps are ignored
    if stripped.isupper() and 4 < len(stripped) <= 80 and " " in stripped:
        return True
    return False


def extract_chapters_from_pdf(pdf_path: Path) -> list[dict]:
    """
    Parse the PDF and split content into chapters.

    Returns a list of dicts with keys: chapter_number, title, content.
    If no chapter headings are found the entire text is returned as one
    chapter titled "Full Text".
    """
    chapters: list[dict] = []
    current_title: str = ""
    current_lines: list[str] = []
    chapter_index: int = 0

    def _flush(title, lines, index):
        return {"chapter_number": index, "title": title or f"Chapter {index}", "content": "\n".join(lines).strip()}

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        logger.info("Total halaman: %d, batch: %d", total_pages, PAGE_BATCH_SIZE)
        for batch_start in range(0, total_pages, PAGE_BATCH_SIZE):
            batch_end = min(batch_start + PAGE_BATCH_SIZE, total_pages)
            logger.info("Proses halaman %d-%d...", batch_start + 1, batch_end)
            for page_num in range(batch_start, batch_end):
                page = pdf.pages[page_num]
                text = page.extract_text() or ""
                page.flush_cache()
                for line in text.splitlines():
                    if _is_chapter_heading(line):
                        if current_lines or current_title:
                            chapters.append(_flush(current_title, current_lines, chapter_index))
                        chapter_index += 1
                        current_title = line.strip()
                        current_lines = []
                    else:
                        current_lines.append(line)
            gc.collect()

    if current_lines or current_title:
        chapters.append(_flush(current_title, current_lines, chapter_index or 1))

    if not chapters:
        full_lines = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                full_lines.append(page.extract_text() or "")
                page.flush_cache()
                gc.collect()
        chapters = [{"chapter_number": 1, "title": "Full Text", "content": "\n".join(full_lines).strip()}]

    return chapters


async def process_book(slug: str) -> None:
    """Extract chapters from the book's PDF and store them in the database."""
    async with AsyncSession(engine) as session:
        result = await session.execute(select(Book).where(Book.slug == slug))
        book = result.scalar_one_or_none()

        if book is None:
            logger.warning("Book '%s' not found in database.", slug)
            return

        if not book.pdf_path or not Path(book.pdf_path).exists():
            logger.warning("PDF not found for book '%s' (path: %s).", slug, book.pdf_path)
            return

        # Remove existing chapters before re-extracting
        existing = await session.execute(
            select(Chapter).where(Chapter.book_id == book.id)
        )
        for ch in existing.scalars().all():
            await session.delete(ch)

        logger.info("Extracting chapters from %s …", book.pdf_path)
        chapters_data = extract_chapters_from_pdf(Path(book.pdf_path))

        for ch_data in chapters_data:
            async with AsyncSession(engine) as s:
                s.add(Chapter(book_id=book.id, **ch_data))
                await s.commit()
        gc.collect()
        logger.info(
            "Stored %d chapters for book '%s'.", len(chapters_data), slug
        )


async def process_all() -> None:
    """Extract chapters for every book that has a local PDF."""
    async with AsyncSession(engine) as session:
        result = await session.execute(
            select(Book.slug).where(Book.pdf_path.isnot(None))
        )
        slugs = [row[0] for row in result.fetchall()]

    logger.info("Processing %d books …", len(slugs))
    for slug in slugs:
        try:
            await process_book(slug)
        except Exception as exc:
            logger.error("Failed to process '%s': %s", slug, exc)


async def main(slug: str | None = None) -> None:
    await create_tables()
    if slug:
        await process_book(slug)
    else:
        await process_all()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract chapters from PDFs.")
    parser.add_argument("--slug", help="Process a single book by slug.")
    args = parser.parse_args()
    asyncio.run(main(slug=args.slug))
