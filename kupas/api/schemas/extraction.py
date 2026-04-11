"""
kupas/api/schemas/extraction.py
Pydantic v2 schemas for the PDF Extraction & Verification API.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExtractionChunkCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=100)
    start_page: int = Field(..., ge=1)
    end_page: int = Field(..., ge=1)
    is_verified: bool = False


class ExtractionChunkOut(BaseModel):
    id: int
    session_id: int
    title: str
    content: str
    start_page: int
    end_page: int
    char_count: int
    word_count: int
    quality_score: float
    is_verified: bool
    order_index: int
    model_config = {"from_attributes": True}


class ExtractionChunkUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    content: Optional[str] = Field(None, min_length=1)
    is_verified: Optional[bool] = None


class ExtractionSessionOut(BaseModel):
    id: int
    book_id: int
    status: str
    total_pages: Optional[int]
    approved_by: Optional[int]
    chunks: List[ExtractionChunkOut] = []
    model_config = {"from_attributes": True}


class ExtractionPreviewResponse(BaseModel):
    chunks: List[ExtractionChunkCreate]
    statistics: Dict[str, Any]
    warnings: List[str]


class SaveExtractionRequest(BaseModel):
    book_id: int = Field(..., ge=1)
    chunks: List[ExtractionChunkCreate]
    total_pages: Optional[int] = None
