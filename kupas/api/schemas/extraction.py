"""
kupas/api/schemas/extraction.py

Pydantic request/response models for the PDF extraction verification API.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ExtractionPreviewRequest(BaseModel):
    """Request body for POST /books/{book_id}/preview-extraction."""
    book_id: int
    use_existing_pdf: bool = True


class ChunkUpdateRequest(BaseModel):
    """Request body for PATCH /extractions/{session_id}/chunks/{chunk_id}."""
    title: Optional[str] = None
    content: Optional[str] = None
    is_verified: Optional[bool] = None


class MergeChunksRequest(BaseModel):
    """Merge two consecutive chunks (current + next)."""
    target_chunk_id: int  # The chunk to merge INTO (the one that follows)


class SplitChunkRequest(BaseModel):
    """Split a chunk at a character offset."""
    split_at: int = Field(..., description="Character index at which to split the content")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class ExtractionChunkResponse(BaseModel):
    id: Optional[int] = None
    session_id: Optional[int] = None
    title: Optional[str]
    content: Optional[str]
    char_count: Optional[int]
    word_count: Optional[int]
    start_page: Optional[int]
    end_page: Optional[int]
    order_index: int = 0
    is_verified: bool = False
    quality_score: Optional[float] = None

    model_config = {"from_attributes": True}


class ExtractionStatistics(BaseModel):
    total_pages: int
    total_chunks: int
    avg_chunk_size: float
    min_chunk_size: int
    max_chunk_size: int
    total_characters: int
    estimated_reading_time_minutes: int


class ExtractionPreviewResponse(BaseModel):
    chunks: List[ExtractionChunkResponse]
    statistics: ExtractionStatistics
    quality_warnings: List[str]


class ExtractionSessionResponse(BaseModel):
    id: int
    book_id: int
    status: str
    total_pages: Optional[int]
    total_chunks: Optional[int]
    approved_by: Optional[int]
    approved_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    chunks: List[ExtractionChunkResponse] = []
    statistics: Optional[ExtractionStatistics] = None
    quality_warnings: List[str] = []

    model_config = {"from_attributes": True}


class ApproveExtractionResponse(BaseModel):
    session_id: int
    status: str
    approved_chunks: int
    message: str
