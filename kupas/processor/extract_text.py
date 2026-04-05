"""
extract_text.py
Ekstrak teks per halaman dari PDF menggunakan PyMuPDF (fitz).
Memory-efficient: proses satu halaman, commit ke DB, hapus dari RAM, lanjut.
"""

import argparse
import asyncio
import gc
import logging
import re
from pathlib import Path

import fitz  # PyMuPDF
from sqlalchemy import select, delete

from kupas.models import Book, Chapter
from kupas.database import create_tables, get_session


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_CHAPTER_RE = re.compile(r"^(BAB\s+[\dIVXivx]+|CHAPTER\s+[\dIVXivx]+)", re.IGNORECASE)


def _is_chapter_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _CHAPTER_RE.match(stripped):
        return True
    if stripped.isupper() and 4 < len(stripped) <= 80 and " " in stripped:
        return True
    return False


async def process_book(slug: str) -> None:
    """Ekstrak teks PDF halaman per halaman, simpan langsung ke DB."""
    async with get_session() as session:
        result = await session.execute(select(Book).where(Book.slug == slug))
        book = result.scalar_one_or_none()
        if book is None:
            logger.warning("Book '%s' tidak ditemukan.", slug)
            return
        if not book.pdf_path or not Path(book.pdf_path).exists():
            logger.warning("PDF tidak ada untuk '%s'.", slug)
            return
        book_id = book.id
        pdf_path = book.pdf_path

    # Hapus chapter lama dulu
    async with get_session() as session:
        await session.execute(delete(Chapter).where(Chapter.book_id == book_id))
        await session.commit()

    logger.info("Mulai ekstraksi: %s", pdf_path)

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    logger.info("Total halaman: %d", total_pages)

    current_title = ""
    current_lines: list[str] = []
    chapter_index = 0

    async def _flush_chapter(title: str, lines: list[str], index: int) -> None:
        if not lines and not title:
            return
        content = "\n".join(lines).strip()
        if not content:
            return
        async with get_session() as s:
            s.add(Chapter(
                book_id=book_id,
                chapter_number=index,
                title=title or f"Chapter {index}",
                content=content,
            ))
            await s.commit()
        logger.info("Disimpan: Chapter %d - %s (%d karakter)", index, title, len(content))

    for page_num in range(total_pages):
        page = doc[page_num]
        text = page.get_text()

        for line in text.splitlines():
            if _is_chapter_heading(line):
                await _flush_chapter(current_title, current_lines, chapter_index)
                chapter_index += 1
                current_title = line.strip()
                current_lines = []
            else:
                current_lines.append(line)

        # Bebaskan memori halaman ini sekarang juga
        del text
        page = None
        if page_num % 20 == 0:
            gc.collect()
            logger.info("Halaman %d/%d selesai...", page_num + 1, total_pages)

    # Flush chapter terakhir
    await _flush_chapter(current_title, current_lines, chapter_index or 1)

    doc.close()
    gc.collect()
    logger.info("Selesai ekstraksi '%s'.", slug)


async def process_all() -> None:
    async with get_session() as session:
        result = await session.execute(select(Book.slug).where(Book.pdf_path.isnot(None)))
        slugs = [row[0] for row in result.fetchall()]
    logger.info("Memproses %d buku...", len(slugs))
    for slug in slugs:
        try:
            await process_book(slug)
        except Exception as exc:
            logger.error("Gagal proses '%s': %s", slug, exc)


async def main(slug: str | None = None) -> None:
    await create_tables()
    if slug:
        await process_book(slug)
    else:
        await process_all()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", help="Proses satu buku berdasarkan slug.")
    args = parser.parse_args()
    asyncio.run(main(slug=args.slug))
