"""
kupas/services/ai_context_builder.py
Builds a verified-only AI prompt context from approved extraction chunks.
"""

from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from kupas.models import ExtractionChunk, ExtractionSession


class AIContextBuilder:
    def __init__(self, db: AsyncSession, max_context_chars: int = 32000):
        self.db = db
        self.max_context_chars = max_context_chars

    async def get_verified_chunks(self, book_id: int) -> List[ExtractionChunk]:
        query = (
            select(ExtractionChunk)
            .join(ExtractionSession)
            .where(
                ExtractionSession.book_id == book_id,
                ExtractionSession.status == "approved",
                ExtractionChunk.is_verified == True,  # noqa: E712
            )
            .order_by(ExtractionChunk.start_page, ExtractionChunk.order_index)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    def build_prompt(self, chunks: List[ExtractionChunk]) -> str:
        if not chunks:
            return ""
        total = sum(c.char_count for c in chunks)
        if total > self.max_context_chars:
            chunks = chunks[: int(len(chunks) * (self.max_context_chars / total))]
        return "\n\n".join(f"## {c.title}\n{c.content}" for c in chunks)
