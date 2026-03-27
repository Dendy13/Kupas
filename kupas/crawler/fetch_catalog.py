"""
fetch_catalog.py
Fetch all book slugs from the Kemdikdasmen catalog API and persist them to
the PostgreSQL database via SQLAlchemy.

Usage:
    python -m kupas.crawler.fetch_catalog
"""

import asyncio
import logging
import os
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/kupas")
CATALOG_API_URL = os.getenv(
    "CATALOG_API_URL",
    "https://api.buku.cloudapp.web.id/getPenggerakTextBooks",
)

engine = create_async_engine(DATABASE_URL, echo=False)


class Base(DeclarativeBase):
    pass


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(unique=True, index=True)
    title: Mapped[str | None]
    author: Mapped[str | None]
    subject: Mapped[str | None]
    grade: Mapped[str | None]
    cover_url: Mapped[str | None]
    pdf_url: Mapped[str | None]
    pdf_path: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def fetch_catalog() -> list[dict]:
    """Fetch the full book catalog from the Kemdikdasmen API."""
    params = {"limit": 2000, "type": "pdf", "order_by": "updated_at"}
    async with httpx.AsyncClient(timeout=60) as client:
        logger.info("Fetching catalog from %s …", CATALOG_API_URL)
        response = await client.get(CATALOG_API_URL, params=params)
        response.raise_for_status()
        data = response.json()

    books: list[dict] = data if isinstance(data, list) else data.get("data", [])
    logger.info("Fetched %d books from catalog.", len(books))
    return books


async def upsert_books(books: list[dict]) -> None:
    """Insert or update books in the database."""
    async with AsyncSession(engine) as session:
        for item in books:
            slug = item.get("slug") or item.get("id")
            if not slug:
                logger.warning("Skipping entry without slug: %s", item)
                continue

            result = await session.execute(select(Book).where(Book.slug == str(slug)))
            existing = result.scalar_one_or_none()

            if existing:
                existing.title = item.get("title") or item.get("nama_buku")
                existing.author = item.get("author") or item.get("penulis")
                existing.subject = item.get("subject") or item.get("mata_pelajaran")
                existing.grade = item.get("grade") or item.get("kelas")
                existing.cover_url = item.get("cover") or item.get("cover_url")
                existing.updated_at = datetime.now(timezone.utc)
            else:
                book = Book(
                    slug=str(slug),
                    title=item.get("title") or item.get("nama_buku"),
                    author=item.get("author") or item.get("penulis"),
                    subject=item.get("subject") or item.get("mata_pelajaran"),
                    grade=item.get("grade") or item.get("kelas"),
                    cover_url=item.get("cover") or item.get("cover_url"),
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
