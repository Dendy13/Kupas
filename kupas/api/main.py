"""
main.py
FastAPI application for the Kupas platform.
"""

import json
import re
import secrets
from contextlib import asynccontextmanager
from typing import AsyncGenerator

# Beralih ke SDK yang baru
from google import genai
import httpx
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kupas.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GCP_PROJECT_ID,
    GCP_REGION,
    DETAIL_API_URL,
    VALID_API_KEYS,
    ALLOWED_ORIGINS,
)
from kupas.models import Book, Chapter, GeneratedContent
from kupas.database import engine, create_tables, get_session

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
    await create_tables()
    yield
    await engine.dispose()

app = FastAPI(
    title="Kupas API",
    description="Platform edukasi — ringkasan & soal latihan dari buku Kemdikdasmen",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)

# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def require_api_key(api_key: str = Depends(api_key_header)) -> None:
    if not VALID_API_KEYS:
        return  # development mode
    if not api_key or not any(secrets.compare_digest(api_key, valid) for valid in VALID_API_KEYS):
        raise HTTPException(status_code=401, detail="API key tidak valid.")

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
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(DETAIL_API_URL, params={"slug": slug})
        resp.raise_for_status()
        return resp.json()

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

# Tambahan Rute Root untuk mencegah 404 Not Found
@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")

@app.get("/books", response_model=list[BookOut], summary="List all books", dependencies=[Depends(require_api_key)])
async def list_books() -> list[BookOut]:
    async with get_session() as session:
        result = await session.execute(select(Book).order_by(Book.title))
        books = result.scalars().all()
    return [BookOut.model_validate(b) for b in books]

@app.get("/books/{slug}", response_model=BookDetailOut, summary="Get book detail with chapters", dependencies=[Depends(require_api_key)])
async def get_book(slug: str) -> BookDetailOut:
    async with get_session() as session:
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

@app.post("/books/{slug}/generate", response_model=GenerateOut, summary="Generate AI summary and practice questions", dependencies=[Depends(require_api_key)])
async def generate(slug: str) -> GenerateOut:
    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY is not configured.",
        )

    async with get_session() as session:
        book = await get_book_or_404(session, slug)

        # Check cache first
        cached = (await session.execute(
            select(GeneratedContent).where(GeneratedContent.book_id == book.id)
        )).scalar_one_or_none()

        if cached:
            return GenerateOut(
                slug=slug,
                summary=cached.summary,
                questions=json.loads(cached.questions_json),
            )

        # Cache miss — load chapters
        chapters = (await session.execute(
            select(Chapter).where(Chapter.book_id == book.id).order_by(Chapter.chapter_number)
        )).scalars().all()

    if not chapters:
        raise HTTPException(
            status_code=404,
            detail=f"No chapters found for book '{slug}'. Run the extractor first.",
        )

    combined_text = "\n\n".join(
        f"[{ch.title}]\n{(ch.content or '')[:3000]}" for ch in chapters
    )
    book_title = book.title or slug

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

    try:
        # Gunakan Vertex AI jika GCP_PROJECT_ID tersedia, fallback ke API key
        if GCP_PROJECT_ID:
            client = genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_REGION)
        else:
            client = genai.Client(api_key=GEMINI_API_KEY)

        # Menggunakan client asynchronous bawaan google-genai
        summary_response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=summary_prompt,
        )
        questions_response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=questions_prompt,
        )

        summary_text = summary_response.text.strip() if summary_response.text else ""
        raw_questions = questions_response.text.strip() if questions_response.text else ""

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Generation failed: {str(e)}")

    question_list = [
        q.strip()
        for q in re.split(r"\n(?=\d+[\.\)])", raw_questions)
        if q.strip()
    ]

    # Save to cache
    async with get_session() as session:
        session.add(GeneratedContent(
            book_id=book.id,
            summary=summary_text,
            questions_json=json.dumps(question_list, ensure_ascii=False),
        ))
        await session.commit()

    return GenerateOut(slug=slug, summary=summary_text, questions=question_list)
