"""
main.py
FastAPI application for the Kupas platform.

Endpoints:
    GET /books              — list all books
    GET /books/{slug}       — book detail + chapters
    GET /generate/{slug}    — AI-generated summary + practice questions via Gemini
"""

import os
import re
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import google.generativeai as genai
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import Text, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/kupas")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
DETAIL_API_URL = os.getenv(
    "DETAIL_API_URL",
    "https://api.buku.cloudapp.web.id/getDetails",
)

engine = create_async_engine(DATABASE_URL, echo=False)

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------


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


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(index=True)
    chapter_number: Mapped[int]
    title: Mapped[str | None]
    content: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------


class ChapterOut(BaseModel):
    id: int
    chapter_number: int
    title: str | None
    content: str | None

    model_config = {"from_attributes": True}


class BookOut(BaseModel):
    id: int
    slug: str
    title: str | None
    author: str | None
    subject: str | None
    grade: str | None
    cover_url: str | None

    model_config = {"from_attributes": True}


class BookDetailOut(BookOut):
    chapters: list[ChapterOut] = []


class GenerateOut(BaseModel):
    slug: str
    summary: str
    questions: list[str]


# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="Kupas API",
    description="Platform edukasi — ringkasan & soal latihan dari buku Kemdikdasmen",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def get_book_or_404(session: AsyncSession, slug: str) -> Book:
    result = await session.execute(select(Book).where(Book.slug == slug))
    book = result.scalar_one_or_none()
    if book is None:
        raise HTTPException(status_code=404, detail=f"Book '{slug}' not found.")
    return book


async def fetch_remote_detail(slug: str) -> dict:
    """Fetch book detail from upstream API (used as fallback)."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(DETAIL_API_URL, params={"slug": slug})
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/books", response_model=list[BookOut], summary="List all books")
async def list_books() -> list[BookOut]:
    async with AsyncSession(engine) as session:
        result = await session.execute(select(Book).order_by(Book.title))
        books = result.scalars().all()
    return [BookOut.model_validate(b) for b in books]


@app.get(
    "/books/{slug}",
    response_model=BookDetailOut,
    summary="Get book detail with chapters",
)
async def get_book(slug: str) -> BookDetailOut:
    async with AsyncSession(engine) as session:
        book = await get_book_or_404(session, slug)

        chapters_result = await session.execute(
            select(Chapter)
            .where(Chapter.book_id == book.id)
            .order_by(Chapter.chapter_number)
        )
        chapters = chapters_result.scalars().all()

    detail = BookDetailOut.model_validate(book)
    detail.chapters = [ChapterOut.model_validate(ch) for ch in chapters]
    return detail


@app.get(
    "/generate/{slug}",
    response_model=GenerateOut,
    summary="Generate AI summary and practice questions",
)
async def generate(slug: str) -> GenerateOut:
    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY is not configured.",
        )

    async with AsyncSession(engine) as session:
        book = await get_book_or_404(session, slug)

        chapters_result = await session.execute(
            select(Chapter)
            .where(Chapter.book_id == book.id)
            .order_by(Chapter.chapter_number)
        )
        chapters = chapters_result.scalars().all()

    if not chapters:
        raise HTTPException(
            status_code=404,
            detail=f"No chapters found for book '{slug}'. Run the extractor first.",
        )

    # Build a condensed text for the AI (limit to keep within token budget)
    combined_text = "\n\n".join(
        f"[{ch.title}]\n{(ch.content or '')[:3000]}" for ch in chapters
    )
    book_title = book.title or slug

    summary_prompt = (
        f"Buku berjudul \"{book_title}\".\n\n"
        f"Berikut adalah isi buku:\n{combined_text}\n\n"
        "Buatkan ringkasan komprehensif dalam Bahasa Indonesia "
        "(maksimal 500 kata)."
    )

    questions_prompt = (
        f"Buku berjudul \"{book_title}\".\n\n"
        f"Berikut adalah isi buku:\n{combined_text}\n\n"
        "Buatkan 10 soal latihan pilihan ganda berbahasa Indonesia "
        "beserta kunci jawabannya."
    )

    model = genai.GenerativeModel(GEMINI_MODEL)
    summary_response = await model.generate_content_async(summary_prompt)
    questions_response = await model.generate_content_async(questions_prompt)

    summary_text: str = summary_response.text.strip()
    raw_questions: str = questions_response.text.strip()

    # Split questions by numbered list items
    question_list = [
        q.strip()
        for q in re.split(r"\n(?=\d+[\.\)])", raw_questions)
        if q.strip()
    ]

    return GenerateOut(slug=slug, summary=summary_text, questions=question_list)
