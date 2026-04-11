"""
kupas/processor/pdf_extractor.py
Smart PDF extractor using PyMuPDF with chapter-based chunking.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


class PDFExtractionError(Exception):
    """Raised when PDF cannot be opened or is unreadable."""


@dataclass
class ExtractionChunk:
    """A single logical chunk extracted from a PDF (typically one chapter)."""

    title: str
    content: str
    start_page: int
    end_page: int
    char_count: int
    word_count: int
    metadata: Dict = field(default_factory=dict)


class PDFExtractor:
    """
    Extract text from PDF bytes using PyMuPDF with smart chunking.

    Chunks are split at chapter boundaries detected via regex, then
    small chunks are merged with the previous one and oversized chunks
    are split at sentence boundaries.
    """

    # Matches lines like "BAB 1", "BAB II", "Bab 3"
    _CHAPTER_RE = re.compile(r"^(BAB|Bab)\s+[\dIVXivx]+", re.IGNORECASE)
    # Page-number-only lines: optional whitespace around 1-4 digits
    _PAGE_NUM_RE = re.compile(r"^\s*\d{1,4}\s*$")
    # Sentence boundary – split on . or \n\n inside long text
    _SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")

    def __init__(
        self,
        min_chunk_size: int = 500,
        max_chunk_size: int = 15_000,
    ) -> None:
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, pdf_bytes: bytes) -> List[ExtractionChunk]:
        """
        Extract text from *pdf_bytes* and return a list of ExtractionChunks
        sorted by page order.

        Algorithm:
        1. Open the PDF in-memory with PyMuPDF.
        2. For every page, collect sorted text blocks.
        3. Detect chapter headings via ``_CHAPTER_RE``.
        4. Flush the current chunk when a new heading is found.
        5. Post-process: merge chunks < min_chunk_size, split > max_chunk_size.

        Raises:
            PDFExtractionError: if the PDF is corrupted or cannot be opened.

        Returns an empty list for PDFs that contain no extractable text.
        """
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            raise PDFExtractionError(f"Tidak dapat membuka PDF: {exc}") from exc

        total_pages = len(doc)
        if total_pages == 0:
            logger.warning("PDF tidak memiliki halaman.")
            return []

        raw_chunks: List[ExtractionChunk] = []

        current_title = "Pendahuluan"
        current_lines: List[str] = []
        current_start = 1

        for page_num in range(total_pages):
            page = doc[page_num]
            page_text = page.get_text("text", sort=True)

            for line in page_text.splitlines():
                if self._is_noise(line):
                    continue

                if self._CHAPTER_RE.match(line.strip()):
                    # Flush current chunk before starting a new one
                    chunk = self._build_chunk(
                        current_title,
                        current_lines,
                        current_start,
                        page_num,  # end page is the *previous* page
                    )
                    if chunk:
                        raw_chunks.append(chunk)
                    current_title = line.strip()
                    current_lines = []
                    current_start = page_num + 1
                else:
                    current_lines.append(line)

        # Flush the last chunk
        chunk = self._build_chunk(
            current_title,
            current_lines,
            current_start,
            total_pages,
        )
        if chunk:
            raw_chunks.append(chunk)

        doc.close()

        chunks = self._post_process(raw_chunks)

        logger.info(
            "Extracted %d chunks from %d pages", len(chunks), total_pages
        )
        return chunks

    def get_statistics(self, chunks: List[ExtractionChunk]) -> Dict:
        """Return quality metrics for a list of ExtractionChunks."""
        if not chunks:
            return {
                "total_chunks": 0,
                "total_chars": 0,
                "total_words": 0,
                "avg_chunk_size": 0,
                "min_chunk_size": 0,
                "max_chunk_size": 0,
                "chunks_below_minimum": 0,
                "chunks_above_maximum": 0,
            }

        char_counts = [c.char_count for c in chunks]
        return {
            "total_chunks": len(chunks),
            "total_chars": sum(char_counts),
            "total_words": sum(c.word_count for c in chunks),
            "avg_chunk_size": round(sum(char_counts) / len(chunks), 1),
            "min_chunk_size": min(char_counts),
            "max_chunk_size": max(char_counts),
            "chunks_below_minimum": sum(
                1 for c in char_counts if c < self.min_chunk_size
            ),
            "chunks_above_maximum": sum(
                1 for c in char_counts if c > self.max_chunk_size
            ),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _is_noise(self, line: str) -> bool:
        """Return True for header/footer/page-number lines to be discarded."""
        stripped = line.strip()
        if not stripped:
            return True
        # Pure page numbers
        if self._PAGE_NUM_RE.match(stripped):
            return True
        # Very short lines (running headers, footers, watermarks)
        if len(stripped) < 15 and not self._CHAPTER_RE.match(stripped):
            return True
        return False

    @staticmethod
    def _build_chunk(
        title: str,
        lines: List[str],
        start_page: int,
        end_page: int,
    ) -> Optional[ExtractionChunk]:
        """Build an ExtractionChunk from accumulated lines; returns None if empty."""
        content = "\n".join(lines).strip()
        if not content:
            return None
        char_count = len(content)
        word_count = len(content.split())
        has_formulas = any(
            kw in content for kw in ("=", "²", "³", "∑", "∫", "√")
        )
        return ExtractionChunk(
            title=title,
            content=content,
            start_page=start_page,
            end_page=end_page,
            char_count=char_count,
            word_count=word_count,
            metadata={"has_formulas": has_formulas, "language": "id"},
        )

    def _post_process(
        self, chunks: List[ExtractionChunk]
    ) -> List[ExtractionChunk]:
        """
        1. Merge chunks that are smaller than *min_chunk_size* into the previous one.
        2. Split chunks larger than *max_chunk_size* at sentence boundaries.
        """
        # --- Merge small chunks ---
        merged: List[ExtractionChunk] = []
        for chunk in chunks:
            if merged and chunk.char_count < self.min_chunk_size:
                prev = merged[-1]
                new_content = prev.content + "\n\n" + chunk.content
                merged[-1] = ExtractionChunk(
                    title=prev.title,
                    content=new_content,
                    start_page=prev.start_page,
                    end_page=chunk.end_page,
                    char_count=len(new_content),
                    word_count=len(new_content.split()),
                    metadata=prev.metadata,
                )
            else:
                merged.append(chunk)

        # --- Split large chunks ---
        result: List[ExtractionChunk] = []
        for chunk in merged:
            if chunk.char_count <= self.max_chunk_size:
                result.append(chunk)
            else:
                result.extend(self._split_chunk(chunk))

        return result

    def _split_chunk(self, chunk: ExtractionChunk) -> List[ExtractionChunk]:
        """Split an oversized chunk at sentence boundaries."""
        sentences = self._SENTENCE_END_RE.split(chunk.content)
        sub_chunks: List[ExtractionChunk] = []
        buffer: List[str] = []
        buffer_len = 0
        part_index = 1

        for sentence in sentences:
            buffer.append(sentence)
            buffer_len += len(sentence) + 1

            if buffer_len >= self.max_chunk_size:
                sub_content = " ".join(buffer).strip()
                sub_chunks.append(
                    ExtractionChunk(
                        title=f"{chunk.title} (bagian {part_index})",
                        content=sub_content,
                        start_page=chunk.start_page,
                        end_page=chunk.end_page,
                        char_count=len(sub_content),
                        word_count=len(sub_content.split()),
                        metadata=chunk.metadata,
                    )
                )
                buffer = []
                buffer_len = 0
                part_index += 1

        if buffer:
            sub_content = " ".join(buffer).strip()
            sub_chunks.append(
                ExtractionChunk(
                    title=f"{chunk.title} (bagian {part_index})",
                    content=sub_content,
                    start_page=chunk.start_page,
                    end_page=chunk.end_page,
                    char_count=len(sub_content),
                    word_count=len(sub_content.split()),
                    metadata=chunk.metadata,
                )
            )

        return sub_chunks or [chunk]
