"""
download_pdf.py
Download PDFs for books stored in the database.

For each book that has no local PDF yet the script:
  1. Calls the detail API to retrieve the download URL from the "attachment" field.
  2. Streams the PDF to kupas/storage/pdf/<slug>.pdf.
  3. Updates the pdf_url and pdf_path columns in the database.

Usage:
    python -m kupas.crawler.download_pdf
    python -m kupas.crawler.download_pdf --slug some-book-slug
"""

import argparse
import asyncio
import logging
from pathlib import Path

import httpx
from sqlalchemy import select

from kupas.config import DETAIL_API_URL, PDF_STORAGE_DIR
from kupas.models import Book
from kupas.database import get_session


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def fetch_detail(slug: str) -> dict:
    """Fetch book detail from the API and return the JSON payload."""
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(DETAIL_API_URL, params={"slug": slug})
        response.raise_for_status()
        return response.json()


def extract_pdf_url(detail: dict) -> str | None:
    """Extract the PDF download URL from the detail response."""
    results = detail.get("results") or detail.get("data") or detail
    if not isinstance(results, dict):
        return None
    return results.get("attachment") or results.get("pdf_url") or results.get("file_url")


async def download_pdf(slug: str, pdf_url: str) -> Path:
    """Stream-download the PDF and save it to storage. Returns the local path."""
    PDF_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    dest = PDF_STORAGE_DIR / f"{slug}.pdf"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; Kupas/1.0; educational use)"}

    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        logger.info("Downloading PDF for '%s' from %s …", slug, pdf_url)
        async with client.stream("GET", pdf_url, headers=headers) as response:
            response.raise_for_status()
            with dest.open("wb") as fh:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    fh.write(chunk)

    logger.info("Saved PDF to %s", dest)
    return dest


async def process_slug(slug: str) -> None:
    """Fetch detail, download PDF, and update the database for a single slug."""
    async with get_session() as session:
        result = await session.execute(select(Book).where(Book.slug == slug))
        book = result.scalar_one_or_none()
        if book is None:
            logger.warning("Slug '%s' not found in database — skipping.", slug)
            return

        if book.pdf_path and Path(book.pdf_path).exists():
            logger.info("PDF for '%s' already exists at %s — skipping.", slug, book.pdf_path)
            return

        detail = await fetch_detail(slug)
        pdf_url = extract_pdf_url(detail)
        if not pdf_url:
            logger.warning("No PDF URL found for slug '%s'.", slug)
            return

        dest = await download_pdf(slug, pdf_url)

        book.pdf_url = pdf_url
        book.pdf_path = str(dest)
        await session.commit()


async def process_all() -> None:
    """Download PDFs for all books that are missing a local file."""
    async with get_session() as session:
        result = await session.execute(select(Book.slug))
        slugs = [row[0] for row in result.fetchall()]

    logger.info("Processing %d books …", len(slugs))
    for slug in slugs:
        try:
            await process_slug(slug)
        except Exception as exc:
            logger.error("Failed to process '%s': %s", slug, exc)


async def main(slug: str | None = None) -> None:
    if slug:
        await process_slug(slug)
    else:
        await process_all()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download PDFs for Kupas books.")
    parser.add_argument("--slug", help="Download a single book by slug.")
    args = parser.parse_args()
    asyncio.run(main(slug=args.slug))
