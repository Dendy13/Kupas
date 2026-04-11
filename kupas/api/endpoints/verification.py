"""
kupas/api/endpoints/verification.py
Admin endpoints for inline chunk verification and session approval.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from kupas.api.schemas.extraction import ExtractionChunkOut, ExtractionSessionOut
from kupas.database import get_session
from kupas.models import Book, ExtractionChunk, ExtractionSession

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin-verification"])


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class ChunkPatchRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    content: Optional[str] = Field(None, min_length=1)
    is_verified: Optional[bool] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_latest_session(book_id: int) -> Optional[ExtractionSession]:
    """Return the most-recently created ExtractionSession for a book, or None."""
    async with get_session() as db:
        result = await db.execute(
            select(ExtractionSession)
            .where(ExtractionSession.book_id == book_id)
            .order_by(ExtractionSession.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/admin/books/{book_id}/extraction",
    response_model=Optional[ExtractionSessionOut],
    summary="Get the latest extraction session (with chunks) for a book",
)
async def get_book_extraction(book_id: int) -> Optional[ExtractionSessionOut]:
    async with get_session() as db:
        book = (
            await db.execute(select(Book).where(Book.id == book_id))
        ).scalar_one_or_none()
        if book is None:
            raise HTTPException(status_code=404, detail=f"Buku ID {book_id} tidak ditemukan.")

        session_row = (
            await db.execute(
                select(ExtractionSession)
                .where(ExtractionSession.book_id == book_id)
                .order_by(ExtractionSession.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        if session_row is None:
            return None

        chunks = (
            await db.execute(
                select(ExtractionChunk)
                .where(ExtractionChunk.session_id == session_row.id)
                .order_by(ExtractionChunk.order_index)
            )
        ).scalars().all()

    return ExtractionSessionOut(
        id=session_row.id,
        book_id=session_row.book_id,
        status=session_row.status,
        total_pages=session_row.total_pages,
        approved_by=session_row.approved_by,
        chunks=[ExtractionChunkOut.model_validate(c) for c in chunks],
    )


@router.patch(
    "/admin/books/{book_id}/chunks/{chunk_id}",
    response_model=ExtractionChunkOut,
    summary="Update title, content or verification status of a chunk",
)
async def patch_chunk(
    book_id: int,
    chunk_id: int,
    payload: ChunkPatchRequest,
) -> ExtractionChunkOut:
    async with get_session() as db:
        # Verify the chunk belongs to a session owned by this book
        result = await db.execute(
            select(ExtractionChunk)
            .join(ExtractionSession)
            .where(
                ExtractionChunk.id == chunk_id,
                ExtractionSession.book_id == book_id,
            )
        )
        chunk = result.scalar_one_or_none()
        if chunk is None:
            raise HTTPException(
                status_code=404,
                detail=f"Chunk {chunk_id} tidak ditemukan untuk buku ID {book_id}.",
            )

        # Guard: prevent editing chunks in an approved session
        session_row = (
            await db.execute(
                select(ExtractionSession).where(ExtractionSession.id == chunk.session_id)
            )
        ).scalar_one_or_none()
        if session_row and session_row.status == "approved":
            raise HTTPException(
                status_code=409,
                detail="Sesi telah disetujui. Chunk tidak dapat diubah.",
            )

        if payload.title is not None:
            chunk.title = payload.title
        if payload.content is not None:
            chunk.content = payload.content
            chunk.char_count = len(payload.content)
            chunk.word_count = len(payload.content.split())
        if payload.is_verified is not None:
            chunk.is_verified = payload.is_verified

        await db.commit()
        await db.refresh(chunk)

    logger.info("Chunk id=%d updated (book_id=%d)", chunk_id, book_id)
    return ExtractionChunkOut.model_validate(chunk)


@router.post(
    "/admin/books/{book_id}/approve-extraction",
    response_model=ExtractionSessionOut,
    summary="Approve the latest extraction session for a book",
)
async def approve_book_extraction(book_id: int) -> ExtractionSessionOut:
    async with get_session() as db:
        book = (
            await db.execute(select(Book).where(Book.id == book_id))
        ).scalar_one_or_none()
        if book is None:
            raise HTTPException(status_code=404, detail=f"Buku ID {book_id} tidak ditemukan.")

        session_row = (
            await db.execute(
                select(ExtractionSession)
                .where(ExtractionSession.book_id == book_id)
                .order_by(ExtractionSession.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if session_row is None:
            raise HTTPException(
                status_code=404,
                detail=f"Tidak ada sesi ekstraksi untuk buku ID {book_id}.",
            )

        session_row.status = "approved"
        await db.commit()
        await db.refresh(session_row)

        chunks = (
            await db.execute(
                select(ExtractionChunk)
                .where(ExtractionChunk.session_id == session_row.id)
                .order_by(ExtractionChunk.order_index)
            )
        ).scalars().all()

    logger.info("ExtractionSession id=%d approved for book_id=%d", session_row.id, book_id)
    return ExtractionSessionOut(
        id=session_row.id,
        book_id=session_row.book_id,
        status=session_row.status,
        total_pages=session_row.total_pages,
        approved_by=session_row.approved_by,
        chunks=[ExtractionChunkOut.model_validate(c) for c in chunks],
    )
