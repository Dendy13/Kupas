"""
kupas/api/endpoints/extraction_verification.py
FastAPI router for the PDF Extraction & Verification workflow.
"""

import logging
from pathlib import Path
from typing import List

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlalchemy import select

from kupas.api.schemas.extraction import (
    ExtractionChunkOut,
    ExtractionChunkUpdate,
    ExtractionPreviewResponse,
    ExtractionSessionOut,
    SaveExtractionRequest,
)
from kupas.database import get_session
from kupas.models import Book, ExtractionChunk, ExtractionSession
from kupas.processor.pdf_extractor import PDFExtractionError, PDFExtractor

logger = logging.getLogger(__name__)
router = APIRouter(tags=["extraction"])

_extractor = PDFExtractor()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _load_pdf_bytes(book: Book) -> bytes:
    """Load PDF bytes from local storage or from a remote URL."""
    if book.pdf_path and Path(book.pdf_path).exists():
        return Path(book.pdf_path).read_bytes()
    if book.pdf_url:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(book.pdf_url)
            resp.raise_for_status()
            return resp.content
    raise HTTPException(
        status_code=404,
        detail="PDF tidak tersedia untuk buku ini (tidak ada pdf_path atau pdf_url).",
    )


def _build_warnings(stats: dict, min_size: int, max_size: int) -> List[str]:
    warnings: List[str] = []
    below = stats.get("chunks_below_minimum", 0)
    above = stats.get("chunks_above_maximum", 0)
    if below:
        warnings.append(f"{below} chunk di bawah ukuran minimum ({min_size} karakter)")
    if above:
        warnings.append(f"{above} chunk di atas ukuran maksimum ({max_size} karakter)")
    return warnings


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/books/{book_id}/preview-extraction",
    response_model=ExtractionPreviewResponse,
    summary="Preview PDF extraction WITHOUT saving to DB",
)
async def preview_extraction(book_id: int) -> ExtractionPreviewResponse:
    """
    Run the PDFExtractor on the book's PDF and return a preview of chunks
    together with statistics and warnings.  Nothing is persisted.
    """
    async with get_session() as session:
        result = await session.execute(select(Book).where(Book.id == book_id))
        book = result.scalar_one_or_none()
        if book is None:
            raise HTTPException(status_code=404, detail=f"Buku ID {book_id} tidak ditemukan.")

    pdf_bytes = await _load_pdf_bytes(book)

    try:
        raw_chunks = _extractor.extract(pdf_bytes)
    except PDFExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not raw_chunks:
        return ExtractionPreviewResponse(chunks=[], statistics={}, warnings=["PDF tidak mengandung teks yang dapat diekstrak."])

    stats = _extractor.get_statistics(raw_chunks)
    warnings = _build_warnings(stats, _extractor.min_chunk_size, _extractor.max_chunk_size)

    from kupas.api.schemas.extraction import ExtractionChunkCreate

    chunk_schemas = [
        ExtractionChunkCreate(
            title=c.title,
            content=c.content,
            start_page=c.start_page,
            end_page=c.end_page,
            is_verified=False,
        )
        for c in raw_chunks
    ]

    return ExtractionPreviewResponse(
        chunks=chunk_schemas,
        statistics=stats,
        warnings=warnings,
    )


@router.post(
    "/extractions",
    response_model=ExtractionSessionOut,
    status_code=201,
    summary="Save verified extraction chunks to the database",
)
async def save_extraction(
    payload: SaveExtractionRequest,
    background_tasks: BackgroundTasks,
) -> ExtractionSessionOut:
    """
    Persist an ExtractionSession with its chunks.  Optionally triggers
    a background AI generation task when all chunks are verified.
    """
    async with get_session() as session:
        result = await session.execute(select(Book).where(Book.id == payload.book_id))
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail=f"Buku ID {payload.book_id} tidak ditemukan.")

        extraction = ExtractionSession(
            book_id=payload.book_id,
            status="draft",
            total_pages=payload.total_pages,
        )
        session.add(extraction)
        await session.flush()  # obtain extraction.id

        for idx, c in enumerate(payload.chunks):
            content = c.content
            session.add(
                ExtractionChunk(
                    session_id=extraction.id,
                    title=c.title,
                    content=content,
                    start_page=c.start_page,
                    end_page=c.end_page,
                    char_count=len(content),
                    word_count=len(content.split()),
                    is_verified=c.is_verified,
                    order_index=idx,
                )
            )

        await session.commit()
        await session.refresh(extraction)

        chunks_result = await session.execute(
            select(ExtractionChunk)
            .where(ExtractionChunk.session_id == extraction.id)
            .order_by(ExtractionChunk.order_index)
        )
        chunks = chunks_result.scalars().all()

    logger.info("Saved ExtractionSession id=%d for book_id=%d", extraction.id, payload.book_id)
    return ExtractionSessionOut(
        id=extraction.id,
        book_id=extraction.book_id,
        status=extraction.status,
        total_pages=extraction.total_pages,
        approved_by=extraction.approved_by,
        chunks=[ExtractionChunkOut.model_validate(ch) for ch in chunks],
    )


@router.patch(
    "/extractions/{extraction_id}/chunks/{chunk_id}",
    response_model=ExtractionChunkOut,
    summary="Edit a single extraction chunk",
)
async def update_chunk(
    extraction_id: int,
    chunk_id: int,
    payload: ExtractionChunkUpdate,
) -> ExtractionChunkOut:
    """Update the title, content or verification status of a chunk."""
    async with get_session() as session:
        result = await session.execute(
            select(ExtractionChunk).where(
                ExtractionChunk.id == chunk_id,
                ExtractionChunk.session_id == extraction_id,
            )
        )
        chunk = result.scalar_one_or_none()
        if chunk is None:
            raise HTTPException(
                status_code=404,
                detail=f"Chunk {chunk_id} tidak ditemukan di sesi {extraction_id}.",
            )

        if payload.title is not None:
            chunk.title = payload.title
        if payload.content is not None:
            chunk.content = payload.content
            chunk.char_count = len(payload.content)
            chunk.word_count = len(payload.content.split())
        if payload.is_verified is not None:
            chunk.is_verified = payload.is_verified

        await session.commit()
        await session.refresh(chunk)

    return ExtractionChunkOut.model_validate(chunk)


@router.post(
    "/extractions/{extraction_id}/approve",
    response_model=ExtractionSessionOut,
    summary="Approve an extraction session and trigger the generation pipeline",
)
async def approve_extraction(
    extraction_id: int,
    background_tasks: BackgroundTasks,
) -> ExtractionSessionOut:
    """
    Mark the ExtractionSession as *approved*.  This endpoint can optionally
    trigger the downstream AI generation pipeline via a background task.
    """
    async with get_session() as session:
        result = await session.execute(
            select(ExtractionSession).where(ExtractionSession.id == extraction_id)
        )
        extraction = result.scalar_one_or_none()
        if extraction is None:
            raise HTTPException(
                status_code=404,
                detail=f"Sesi ekstraksi {extraction_id} tidak ditemukan.",
            )

        extraction.status = "approved"
        await session.commit()
        await session.refresh(extraction)

        chunks_result = await session.execute(
            select(ExtractionChunk)
            .where(ExtractionChunk.session_id == extraction.id)
            .order_by(ExtractionChunk.order_index)
        )
        chunks = chunks_result.scalars().all()

    logger.info("ExtractionSession id=%d approved.", extraction_id)

    return ExtractionSessionOut(
        id=extraction.id,
        book_id=extraction.book_id,
        status=extraction.status,
        total_pages=extraction.total_pages,
        approved_by=extraction.approved_by,
        chunks=[ExtractionChunkOut.model_validate(ch) for ch in chunks],
    )
