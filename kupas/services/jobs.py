"""
kupas/services/jobs.py
Centralized background job logic for the Kupas admin pipeline.
"""

import json
import logging
import re

from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError

from kupas.config import GEMINI_API_KEY, GEMINI_MODEL, GCP_PROJECT_ID, GCP_REGION
from kupas.database import get_session
from kupas.models import Book, Chapter, GeneratedContent, JobLog

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Job log helpers
# ---------------------------------------------------------------------------


async def log_job(
    job_type: str,
    slug: str | None = None,
    status: str = "pending",
    message: str | None = None,
) -> int:
    """Create a job log entry and return its id."""
    async with get_session() as session:
        job = JobLog(job_type=job_type, slug=slug, status=status, message=message)
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job.id


async def update_job(job_id: int, status: str, message: str | None = None) -> None:
    """Update job status and message."""
    async with get_session() as session:
        result = await session.execute(select(JobLog).where(JobLog.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            logger.warning("Job %d not found for update.", job_id)
            return
        job.status = status
        if message is not None:
            job.message = message
        await session.commit()


# ---------------------------------------------------------------------------
# Pipeline functions
# ---------------------------------------------------------------------------


async def run_fetch_catalog(job_id: int) -> None:
    """Fetch the full catalog from Kemdikdasmen API and upsert into DB."""
    from kupas.crawler.fetch_catalog import fetch_catalog, upsert_books

    try:
        await update_job(job_id, "running")
        books = await fetch_catalog()
        await upsert_books(books)
        count = len(books)
        await update_job(job_id, "done", f"Fetched {count} books")
    except Exception as exc:
        logger.exception("run_fetch_catalog failed")
        await update_job(job_id, "error", str(exc))


async def run_download_pdf(job_id: int, slug: str) -> None:
    """Download PDF for a single book slug."""
    from kupas.crawler.download_pdf import process_slug

    try:
        await update_job(job_id, "running")
        await process_slug(slug)
        await update_job(job_id, "done", "PDF downloaded")
    except Exception as exc:
        logger.exception("run_download_pdf failed for '%s'", slug)
        await update_job(job_id, "error", str(exc))


async def run_download_all_pdfs(job_id: int) -> None:
    """Download PDFs for all books that are missing a local file."""
    from kupas.crawler.download_pdf import process_slug

    try:
        await update_job(job_id, "running")
        async with get_session() as session:
            result = await session.execute(
                select(Book.slug).where(Book.pdf_path.is_(None))
            )
            slugs = [row[0] for row in result.fetchall()]

        total = len(slugs)
        downloaded = 0
        for slug in slugs:
            try:
                await process_slug(slug)
                downloaded += 1
                await update_job(job_id, "running", f"{downloaded}/{total} downloaded")
            except Exception as exc:
                logger.error("Failed to download PDF for '%s': %s", slug, exc)

        await update_job(job_id, "done", "All PDFs downloaded")
    except Exception as exc:
        logger.exception("run_download_all_pdfs failed")
        await update_job(job_id, "error", str(exc))


async def run_extract_text(job_id: int, slug: str) -> None:
    """Extract chapters from the PDF for a single book slug."""
    from kupas.processor.extract_text import process_book

    try:
        await update_job(job_id, "running")
        await process_book(slug)
        async with get_session() as session:
            result = await session.execute(
                select(Book).where(Book.slug == slug)
            )
            book = result.scalar_one_or_none()
            chapter_count = 0
            if book:
                chapters_result = (
                    await session.execute(
                        select(Chapter).where(Chapter.book_id == book.id)
                    )
                ).scalars().all()
                chapter_count = len(chapters_result)
        await update_job(job_id, "done", f"Extracted {chapter_count} chapters")
    except Exception as exc:
        logger.exception("run_extract_text failed for '%s'", slug)
        await update_job(job_id, "error", str(exc))


async def run_extract_all(job_id: int) -> None:
    """Extract chapters from PDFs for all books that have a pdf_path."""
    from kupas.processor.extract_text import process_book

    try:
        await update_job(job_id, "running")
        async with get_session() as session:
            result = await session.execute(
                select(Book.slug).where(Book.pdf_path.isnot(None))
            )
            slugs = [row[0] for row in result.fetchall()]

        total = len(slugs)
        processed = 0
        for slug in slugs:
            try:
                await process_book(slug)
                processed += 1
                await update_job(job_id, "running", f"{processed}/{total} extracted")
            except Exception as exc:
                logger.error("Failed to extract '%s': %s", slug, exc)

        await update_job(job_id, "done", "All books extracted")
    except Exception as exc:
        logger.exception("run_extract_all failed")
        await update_job(job_id, "error", str(exc))


async def _generate_for_book(book: Book) -> tuple[str, list[str]]:
    """Call Gemini to generate summary and questions for a single book."""
    from google import genai

    async with get_session() as session:
        chapters = (
            await session.execute(
                select(Chapter)
                .where(Chapter.book_id == book.id)
                .order_by(Chapter.chapter_number)
            )
        ).scalars().all()

    if not chapters:
        raise ValueError(f"No chapters for book '{book.slug}'")

    combined_text = "\n\n".join(
        f"[{ch.title}]\n{(ch.content or '')[:3000]}" for ch in chapters
    )
    book_title = book.title or book.slug

    summary_prompt = (
        f"Buku berjudul \"{book_title}\".\n\n"
        f"Berikut adalah isi buku:\n{combined_text}\n\n"
        "Buatkan ringkasan komprehensif dalam Bahasa Indonesia (maksimal 500 kata)."
    )
    questions_prompt = (
        f"Buku berjudul \"{book_title}\".\n\n"
        f"Berikut adalah isi buku:\n{combined_text}\n\n"
        "Buatkan 10 soal latihan pilihan ganda berbahasa Indonesia beserta kunci jawabannya."
    )

    if GCP_PROJECT_ID:
        client = genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_REGION)
    else:
        client = genai.Client(api_key=GEMINI_API_KEY)

    summary_response = await client.aio.models.generate_content(
        model=GEMINI_MODEL, contents=summary_prompt
    )
    questions_response = await client.aio.models.generate_content(
        model=GEMINI_MODEL, contents=questions_prompt
    )

    summary_text = summary_response.text.strip() if summary_response.text else ""
    raw_questions = questions_response.text.strip() if questions_response.text else ""
    question_list = [
        q.strip()
        for q in re.split(r"\n(?=\d+[\.\)])", raw_questions)
        if q.strip()
    ]
    return summary_text, question_list


async def run_generate_for_book(job_id: int, slug: str) -> None:
    """Generate AI content for a single book by slug."""
    try:
        await update_job(job_id, "running")
        async with get_session() as session:
            result = await session.execute(select(Book).where(Book.slug == slug))
            book = result.scalar_one_or_none()
        if book is None:
            await update_job(job_id, "error", f"Book '{slug}' not found")
            return
        summary_text, question_list = await _generate_for_book(book)
        async with get_session() as session:
            try:
                session.add(GeneratedContent(
                    book_id=book.id,
                    summary=summary_text,
                    questions_json=json.dumps(question_list, ensure_ascii=False),
                ))
                await session.commit()
            except IntegrityError:
                await session.rollback()
        await update_job(job_id, "done", f"Generated for '{slug}'")
    except Exception as exc:
        logger.exception("run_generate_for_book failed for '%s'", slug)
        await update_job(job_id, "error", str(exc))
    """Generate AI content for all books that have chapters but no GeneratedContent."""
    try:
        await update_job(job_id, "running")

        async with get_session() as session:
            # Books that have at least one chapter
            books_with_chapters_result = await session.execute(
                select(Book)
                .join(Chapter, Chapter.book_id == Book.id)
                .outerjoin(GeneratedContent, GeneratedContent.book_id == Book.id)
                .where(GeneratedContent.id.is_(None))
                .distinct()
            )
            books = books_with_chapters_result.scalars().all()

        total = len(books)
        generated = 0
        for book in books:
            try:
                summary_text, question_list = await _generate_for_book(book)
                async with get_session() as session:
                    try:
                        session.add(GeneratedContent(
                            book_id=book.id,
                            summary=summary_text,
                            questions_json=json.dumps(question_list, ensure_ascii=False),
                        ))
                        await session.commit()
                    except IntegrityError:
                        await session.rollback()
                generated += 1
                await update_job(job_id, "running", f"{generated}/{total} generated")
            except Exception as exc:
                logger.error("Failed to generate AI for '%s': %s", book.slug, exc)

        await update_job(job_id, "done", f"Generated for {generated} books")
    except Exception as exc:
        logger.exception("run_generate_all failed")
        await update_job(job_id, "error", str(exc))
