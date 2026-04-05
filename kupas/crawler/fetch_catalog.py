"""
fetch_catalog.py
Fetch all book slugs from the Kemdikdasmen catalog API and persist them to
the PostgreSQL database via SQLAlchemy.

Usage:
    python -m kupas.crawler.fetch_catalog
"""

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from kupas.config import CATALOG_API_URL
from kupas.models import Book
from kupas.database import create_tables, get_session


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def fetch_catalog() -> list[dict]:
    """Fetch the full book catalog from the Kemdikdasmen API."""
    url = f"{CATALOG_API_URL}?limit=2000&type=pdf&order_by=updated_at"
    async with httpx.AsyncClient(timeout=60) as client:
        logger.info("Fetching catalog from %s …", CATALOG_API_URL)
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()

    books: list[dict] = data if isinstance(data, list) else data.get("data") or data.get("results") or []
    logger.info("Fetched %d books from catalog.", len(books))
    return books


async def upsert_books(books: list[dict]) -> None:
    """Insert or update books in the database."""
    async with get_session() as session:
        for item in books:
            slug = item.get("slug") or item.get("id")
            if not slug:
                logger.warning("Skipping entry without slug: %s", item)
                continue

            result = await session.execute(select(Book).where(Book.slug == str(slug)))
            existing = result.scalar_one_or_none()

            if existing:
                existing.title = item.get("title") or item.get("nama_buku")
                existing.author = item.get("writer") or item.get("author") or item.get("penulis")
                existing.subject = item.get("subject") or item.get("mata_pelajaran")
                existing.grade = item.get("class") or item.get("grade") or item.get("kelas")
                existing.cover_url = item.get("image") or item.get("cover") or item.get("cover_url")
                existing.updated_at = datetime.now(timezone.utc)
            else:
                book = Book(
                    slug=str(slug),
                    title=item.get("title") or item.get("nama_buku"),
                    author=item.get("writer") or item.get("author") or item.get("penulis"),
                    subject=item.get("subject") or item.get("mata_pelajaran"),
                    grade=item.get("class") or item.get("grade") or item.get("kelas"),
                    cover_url=item.get("image") or item.get("cover") or item.get("cover_url"),
                )
                session.add(book)

        await session.commit()
        logger.info("Database updated with catalog entries.")


async def main() -> None:
    await create_tables()
    books = await fetch_catalog()
    await upsert_books(books)


if __name__ == "__main__":
    asyncio.run(main())
