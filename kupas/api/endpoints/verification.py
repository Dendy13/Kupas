"""
kupas/api/endpoints/verification.py

FastAPI router for PDF extraction verification.

Endpoints
---------
POST   /books/{book_id}/preview-extraction
         Run (or re-run) extraction and return results without persisting.
POST   /books/{book_id}/extractions
         Run extraction and persist a new ExtractionSession to the database.
GET    /extractions/{session_id}
         Return a saved ExtractionSession with its chunks and quality stats.
PATCH  /extractions/{session_id}/chunks/{chunk_id}
         Update chunk content / verified flag.
POST   /extractions/{session_id}/chunks/{chunk_id}/merge
         Merge a chunk with its successor.
POST   /extractions/{session_id}/chunks/{chunk_id}/split
         Split a chunk at a given character offset.
POST   /extractions/{session_id}/approve
         Mark a session as approved (triggers chapter sync).
"""

import logging
import math
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from kupas.api.schemas.extraction import (
    ApproveExtractionResponse,
    ChunkUpdateRequest,
    ExtractionChunkResponse,
    ExtractionPreviewRequest,
    ExtractionPreviewResponse,
    ExtractionSessionResponse,
    ExtractionStatistics,
    MergeChunksRequest,
    SplitChunkRequest,
)
from kupas.database import get_session
from kupas.models import Book, Chapter, ExtractionChunk, ExtractionSession
from kupas.processor.pdf_extractor import PDFExtractor, PDFExtractionError

router = APIRouter(prefix="/api", tags=["extraction"])


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _quality_score(char_count: int, min_size: int = 500, max_size: int = 15_000) -> float:
    """Return a 0.0–1.0 quality score based on chunk size."""
    if char_count < min_size:
        return round(char_count / min_size * 0.5, 3)
    if char_count > max_size:
        return round(max(0.5, 1.0 - (char_count - max_size) / max_size * 0.3), 3)
    return 1.0


def _compute_statistics(
    chunks: List[ExtractionChunkResponse],
    total_pages: int,
) -> ExtractionStatistics:
    sizes = [c.char_count or 0 for c in chunks]
    total_chars = sum(sizes)
    avg = total_chars / len(sizes) if sizes else 0.0
    total_words = sum(c.word_count or 0 for c in chunks)
    return ExtractionStatistics(
        total_pages=total_pages,
        total_chunks=len(chunks),
        avg_chunk_size=round(avg, 1),
        min_chunk_size=min(sizes, default=0),
        max_chunk_size=max(sizes, default=0),
        total_characters=total_chars,
        estimated_reading_time_minutes=max(1, math.ceil(total_words / 200)),
    )


def _quality_warnings(chunks: List[ExtractionChunkResponse]) -> List[str]:
    warnings: List[str] = []
    small = sum(1 for c in chunks if (c.char_count or 0) < 500)
    large = sum(1 for c in chunks if (c.char_count or 0) > 15_000)
    if small:
        warnings.append(f"{small} chunk(s) di bawah ukuran minimum (500 karakter)")
    if large:
        warnings.append(f"{large} chunk(s) melebihi ukuran maksimum (15.000 karakter)")
    if not chunks:
        warnings.append("Tidak ada chunk yang berhasil diekstrak")
    return warnings


def _chunk_to_response(
    chunk: "ExtractionChunk",
) -> ExtractionChunkResponse:
    return ExtractionChunkResponse(
        id=chunk.id,
        session_id=chunk.session_id,
        title=chunk.title,
        content=chunk.content,
        char_count=chunk.char_count,
        word_count=chunk.word_count,
        start_page=chunk.start_page,
        end_page=chunk.end_page,
        order_index=chunk.order_index,
        is_verified=chunk.is_verified,
        quality_score=chunk.quality_score,
    )


async def _get_book_or_404(session: AsyncSession, book_id: int) -> Book:
    result = await session.execute(select(Book).where(Book.id == book_id))
    book = result.scalar_one_or_none()
    if book is None:
        raise HTTPException(status_code=404, detail=f"Book {book_id} tidak ditemukan.")
    return book


async def _get_session_or_404(
    db: AsyncSession, session_id: int
) -> ExtractionSession:
    result = await db.execute(
        select(ExtractionSession)
        .where(ExtractionSession.id == session_id)
    )
    sess = result.scalar_one_or_none()
    if sess is None:
        raise HTTPException(status_code=404, detail=f"ExtractionSession {session_id} tidak ditemukan.")
    return sess


async def _get_chunk_or_404(
    db: AsyncSession, session_id: int, chunk_id: int
) -> ExtractionChunk:
    result = await db.execute(
        select(ExtractionChunk)
        .where(
            ExtractionChunk.id == chunk_id,
            ExtractionChunk.session_id == session_id,
        )
    )
    chunk = result.scalar_one_or_none()
    if chunk is None:
        raise HTTPException(
            status_code=404,
            detail=f"Chunk {chunk_id} tidak ditemukan dalam session {session_id}.",
        )
    return chunk


def _extract_from_book(book: Book) -> tuple[List[ExtractionChunkResponse], int]:
    """
    Run PDF extraction for a book and return (chunk_responses, total_pages).
    Raises HTTPException on extraction failure.
    """
    if not book.pdf_path or not Path(book.pdf_path).exists():
        raise HTTPException(
            status_code=422,
            detail=f"PDF tidak tersedia untuk buku '{book.slug}'.",
        )

    extractor = PDFExtractor()
    try:
        raw_chunks = extractor.extract_from_path(book.pdf_path)
    except PDFExtractionError as exc:
        raise HTTPException(status_code=422, detail=f"Gagal ekstrak PDF: {exc}") from exc

    stats = extractor.get_statistics()
    total_pages: int = stats.get("total_pages", 0)

    chunk_responses = [
        ExtractionChunkResponse(
            title=c.title,
            content=c.content,
            char_count=c.char_count,
            word_count=c.word_count,
            start_page=c.start_page,
            end_page=c.end_page,
            order_index=i,
            is_verified=False,
            quality_score=_quality_score(c.char_count),
        )
        for i, c in enumerate(raw_chunks)
    ]
    return chunk_responses, total_pages


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/books/{book_id}/preview-extraction",
    response_model=ExtractionPreviewResponse,
    summary="Preview PDF extraction without saving to database",
)
async def preview_extraction(book_id: int) -> ExtractionPreviewResponse:
    """
    Run PDF extraction for *book_id* and return the results **without**
    persisting anything to the database.  Useful for previewing before commit.
    """
    async with get_session() as db:
        book = await _get_book_or_404(db, book_id)
        chunk_responses, total_pages = _extract_from_book(book)

    statistics = _compute_statistics(chunk_responses, total_pages)
    warnings = _quality_warnings(chunk_responses)
    return ExtractionPreviewResponse(
        chunks=chunk_responses,
        statistics=statistics,
        quality_warnings=warnings,
    )


@router.post(
    "/books/{book_id}/extractions",
    response_model=ExtractionSessionResponse,
    status_code=201,
    summary="Run extraction and persist a new ExtractionSession",
)
async def create_extraction(book_id: int) -> ExtractionSessionResponse:
    """
    Extract the book's PDF and save the session + all chunks to the database.
    Returns the new :class:`ExtractionSession` (status = ``"draft"``).
    """
    async with get_session() as db:
        book = await _get_book_or_404(db, book_id)
        chunk_responses, total_pages = _extract_from_book(book)

        ext_session = ExtractionSession(
            book_id=book_id,
            status="draft",
            total_pages=total_pages,
            total_chunks=len(chunk_responses),
        )
        db.add(ext_session)
        await db.flush()  # obtain ext_session.id

        for cr in chunk_responses:
            db.add(ExtractionChunk(
                session_id=ext_session.id,
                title=cr.title,
                content=cr.content,
                char_count=cr.char_count,
                word_count=cr.word_count,
                start_page=cr.start_page,
                end_page=cr.end_page,
                order_index=cr.order_index,
                quality_score=cr.quality_score,
                is_verified=False,
            ))

        await db.commit()
        await db.refresh(ext_session)

    async with get_session() as db:
        result = await db.execute(
            select(ExtractionChunk)
            .where(ExtractionChunk.session_id == ext_session.id)
            .order_by(ExtractionChunk.order_index)
        )
        db_chunks = result.scalars().all()

    chunk_resp = [_chunk_to_response(c) for c in db_chunks]
    stats = _compute_statistics(chunk_resp, total_pages)
    warnings = _quality_warnings(chunk_resp)
    return ExtractionSessionResponse(
        id=ext_session.id,
        book_id=ext_session.book_id,
        status=ext_session.status,
        total_pages=ext_session.total_pages,
        total_chunks=ext_session.total_chunks,
        approved_by=ext_session.approved_by,
        approved_at=ext_session.approved_at,
        created_at=ext_session.created_at,
        updated_at=ext_session.updated_at,
        chunks=chunk_resp,
        statistics=stats,
        quality_warnings=warnings,
    )


@router.get(
    "/extractions/{session_id}",
    response_model=ExtractionSessionResponse,
    summary="Get a saved ExtractionSession with chunks and quality metrics",
)
async def get_extraction(session_id: int) -> ExtractionSessionResponse:
    async with get_session() as db:
        ext_session = await _get_session_or_404(db, session_id)
        result = await db.execute(
            select(ExtractionChunk)
            .where(ExtractionChunk.session_id == session_id)
            .order_by(ExtractionChunk.order_index)
        )
        db_chunks = result.scalars().all()

    chunk_resp = [_chunk_to_response(c) for c in db_chunks]
    stats = _compute_statistics(chunk_resp, ext_session.total_pages or 0)
    warnings = _quality_warnings(chunk_resp)
    return ExtractionSessionResponse(
        id=ext_session.id,
        book_id=ext_session.book_id,
        status=ext_session.status,
        total_pages=ext_session.total_pages,
        total_chunks=ext_session.total_chunks,
        approved_by=ext_session.approved_by,
        approved_at=ext_session.approved_at,
        created_at=ext_session.created_at,
        updated_at=ext_session.updated_at,
        chunks=chunk_resp,
        statistics=stats,
        quality_warnings=warnings,
    )


@router.patch(
    "/extractions/{session_id}/chunks/{chunk_id}",
    response_model=ExtractionChunkResponse,
    summary="Update chunk content or verification status",
)
async def update_chunk(
    session_id: int,
    chunk_id: int,
    body: ChunkUpdateRequest,
) -> ExtractionChunkResponse:
    async with get_session() as db:
        chunk = await _get_chunk_or_404(db, session_id, chunk_id)

        if body.title is not None:
            chunk.title = body.title
        if body.content is not None:
            chunk.content = body.content
            words = body.content.split()
            chunk.char_count = len(body.content)
            chunk.word_count = len(words)
            chunk.quality_score = _quality_score(chunk.char_count)
        if body.is_verified is not None:
            chunk.is_verified = body.is_verified

        await db.commit()
        await db.refresh(chunk)

    return _chunk_to_response(chunk)


@router.post(
    "/extractions/{session_id}/chunks/{chunk_id}/merge",
    response_model=ExtractionChunkResponse,
    summary="Merge this chunk with its successor",
)
async def merge_chunk(
    session_id: int,
    chunk_id: int,
    body: MergeChunksRequest,
) -> ExtractionChunkResponse:
    """
    Merge *chunk_id* with *body.target_chunk_id*.
    The target chunk must belong to the same session and come after chunk_id.
    Content is concatenated; the target chunk is then deleted.
    """
    async with get_session() as db:
        source = await _get_chunk_or_404(db, session_id, chunk_id)
        target = await _get_chunk_or_404(db, session_id, body.target_chunk_id)

        if source.order_index >= target.order_index:
            raise HTTPException(
                status_code=422,
                detail="target_chunk_id harus berada setelah chunk_id (order_index lebih besar).",
            )

        combined = (source.content or "") + "\n\n" + (target.content or "")
        source.content = combined.strip()
        source.end_page = target.end_page
        source.char_count = len(source.content)
        source.word_count = len(source.content.split())
        source.quality_score = _quality_score(source.char_count)

        await db.delete(target)
        await db.commit()
        await db.refresh(source)

    return _chunk_to_response(source)


@router.post(
    "/extractions/{session_id}/chunks/{chunk_id}/split",
    response_model=List[ExtractionChunkResponse],
    summary="Split a chunk at a given character offset",
)
async def split_chunk(
    session_id: int,
    chunk_id: int,
    body: SplitChunkRequest,
) -> List[ExtractionChunkResponse]:
    async with get_session() as db:
        chunk = await _get_chunk_or_404(db, session_id, chunk_id)
        content = chunk.content or ""

        if body.split_at <= 0 or body.split_at >= len(content):
            raise HTTPException(
                status_code=422,
                detail=f"split_at ({body.split_at}) harus berada di dalam konten (1 – {len(content) - 1}).",
            )

        part_a = content[: body.split_at].strip()
        part_b = content[body.split_at :].strip()

        chunk.content = part_a
        chunk.char_count = len(part_a)
        chunk.word_count = len(part_a.split())
        chunk.quality_score = _quality_score(chunk.char_count)

        new_chunk = ExtractionChunk(
            session_id=session_id,
            title=f"{chunk.title} (lanjutan)",
            content=part_b,
            start_page=chunk.start_page,
            end_page=chunk.end_page,
            char_count=len(part_b),
            word_count=len(part_b.split()),
            quality_score=_quality_score(len(part_b)),
            order_index=chunk.order_index + 1,
            is_verified=False,
        )
        db.add(new_chunk)
        await db.commit()
        await db.refresh(chunk)
        await db.refresh(new_chunk)

    return [_chunk_to_response(chunk), _chunk_to_response(new_chunk)]


@router.post(
    "/extractions/{session_id}/approve",
    response_model=ApproveExtractionResponse,
    summary="Approve extraction and sync chapters to the book",
)
async def approve_extraction(session_id: int) -> ApproveExtractionResponse:
    """
    Mark the extraction session as *approved* and copy each chunk into the
    book's ``chapters`` table so the existing generation pipeline can use them.
    """
    async with get_session() as db:
        ext_session = await _get_session_or_404(db, session_id)

        if ext_session.status == "approved":
            raise HTTPException(
                status_code=409,
                detail="Session sudah disetujui sebelumnya.",
            )

        result = await db.execute(
            select(ExtractionChunk)
            .where(ExtractionChunk.session_id == session_id)
            .order_by(ExtractionChunk.order_index)
        )
        db_chunks = result.scalars().all()

        if not db_chunks:
            raise HTTPException(
                status_code=422,
                detail="Tidak ada chunk untuk disetujui.",
            )

        # Replace book's chapters with extraction chunks
        await db.execute(
            sa_delete(Chapter).where(Chapter.book_id == ext_session.book_id)
        )
        for idx, chunk in enumerate(db_chunks, start=1):
            db.add(Chapter(
                book_id=ext_session.book_id,
                chapter_number=idx,
                title=chunk.title or f"Bab {idx}",
                content=chunk.content,
            ))

        ext_session.status = "approved"
        ext_session.total_chunks = len(db_chunks)
        await db.commit()

    return ApproveExtractionResponse(
        session_id=session_id,
        status="approved",
        approved_chunks=len(db_chunks),
        message=f"Session disetujui. {len(db_chunks)} chapter disinkronkan ke buku.",
    )
