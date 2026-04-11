"""
kupas/processor/pdf_extractor.py

Hybrid PDF extractor with smart chunking for Indonesian Kemendikbud ebooks.
Uses PyMuPDF (fitz) with chapter-boundary detection, noise filtering,
and automatic chunk merging/splitting.
"""

import gc
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class PDFExtractionError(Exception):
    """Raised when the PDF cannot be opened or read."""


class ExtractionTimeoutError(Exception):
    """Raised when extraction exceeds the time limit."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ExtractionChunk:
    """A single logical chunk (usually one chapter) extracted from a PDF."""

    title: str
    content: str
    start_page: int
    end_page: int
    char_count: int
    word_count: int
    metadata: Dict = field(default_factory=dict)

    @classmethod
    def from_raw(
        cls,
        title: str,
        content: str,
        start_page: int,
        end_page: int,
    ) -> "ExtractionChunk":
        words = content.split()
        has_math = bool(
            re.search(r"[=+\-*/^√∑∫∏]|\d+\s*/\s*\d+|\bsin\b|\bcos\b|\blog\b", content)
        )
        return cls(
            title=title,
            content=content,
            start_page=start_page,
            end_page=end_page,
            char_count=len(content),
            word_count=len(words),
            metadata={
                "has_mathematical_formulas": has_math,
                "reading_time_minutes": max(1, len(words) // 200),
            },
        )


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

class PDFExtractor:
    """
    Extracts text from a PDF file and groups it into logical chunks.

    Strategy
    --------
    1. Open the PDF with PyMuPDF using sorted text blocks (handles columns).
    2. Collect every page's text, tracking line-level repetition across
       multiple pages (header/footer noise).
    3. Walk lines to detect chapter boundaries.
    4. Flush a chunk whenever a new chapter starts, merging it with the
       previous chunk when it is too small, and splitting when too large.

    Parameters
    ----------
    min_chunk_size : int
        Minimum number of characters for a standalone chunk.
    max_chunk_size : int
        Maximum number of characters before a chunk is split.
    """

    # Patterns that indicate a chapter / major section heading
    _CHAPTER_RE = re.compile(
        r"^(BAB|Bab|CHAPTER|Chapter)\s+[\dIVXivx]+",
        re.IGNORECASE,
    )

    def __init__(
        self,
        min_chunk_size: int = 500,
        max_chunk_size: int = 15_000,
    ) -> None:
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self._stats: Dict = {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def extract(self, pdf_bytes: bytes) -> List[ExtractionChunk]:
        """
        Extract and return chunks from raw PDF bytes.

        Parameters
        ----------
        pdf_bytes : bytes
            Raw bytes of the PDF file.

        Returns
        -------
        List[ExtractionChunk]
            Ordered list of extracted chunks (may be empty for blank PDFs).

        Raises
        ------
        PDFExtractionError
            If the PDF cannot be opened or is corrupted.
        """
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            raise PDFExtractionError(f"Cannot open PDF: {exc}") from exc

        if doc.page_count == 0:
            logger.warning("PDF has 0 pages — returning empty extraction.")
            doc.close()
            return []

        try:
            return self._run_extraction(doc)
        finally:
            doc.close()
            gc.collect()

    def extract_from_path(self, pdf_path: str) -> List[ExtractionChunk]:
        """Convenience wrapper: read file from disk and call extract()."""
        try:
            with open(pdf_path, "rb") as fh:
                pdf_bytes = fh.read()
        except OSError as exc:
            raise PDFExtractionError(f"Cannot read PDF file '{pdf_path}': {exc}") from exc
        return self.extract(pdf_bytes)

    def get_statistics(self) -> Dict:
        """Return statistics from the most recent extraction."""
        return dict(self._stats)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_extraction(self, doc: fitz.Document) -> List[ExtractionChunk]:
        total_pages = doc.page_count
        logger.info("Starting extraction: %d pages", total_pages)

        # --- Pass 1: collect all lines per page ---
        pages_lines: List[List[str]] = []
        for page_num in range(total_pages):
            page = doc[page_num]
            text = page.get_text(sort=True)  # sort=True → reading order / columns
            lines = text.splitlines()
            pages_lines.append(lines)
            if page_num % 20 == 0:
                logger.info("Reading page %d/%d", page_num + 1, total_pages)

        # --- Identify noise lines (headers/footers) ---
        noise = self._detect_noise(pages_lines)

        # --- Pass 2: group lines into chapter chunks ---
        raw_chunks: List[tuple[str, List[str], int, int]] = []  # (title, lines, start, end)
        current_title = ""
        current_lines: List[str] = []
        current_start = 0

        def flush(title: str, lines: List[str], start: int, end: int) -> None:
            if lines or title:
                raw_chunks.append((title, lines[:], start, end))

        for page_num, lines in enumerate(pages_lines):
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped in noise:
                    continue
                if self._is_standalone_number(stripped):
                    continue

                if self._is_chapter_heading(stripped):
                    flush(current_title, current_lines, current_start, page_num)
                    # Avoid duplicate consecutive headings
                    current_title = stripped
                    current_lines = []
                    current_start = page_num
                else:
                    current_lines.append(stripped)

        flush(current_title, current_lines, current_start, total_pages - 1)

        # --- Build ExtractionChunk objects ---
        chunks = self._build_chunks(raw_chunks)

        # --- Merge small chunks, split large ones ---
        chunks = self._merge_small_chunks(chunks)
        chunks = self._split_large_chunks(chunks)

        self._stats = {
            "total_pages": total_pages,
            "total_chunks": len(chunks),
            "avg_chunk_size": (
                sum(c.char_count for c in chunks) / len(chunks) if chunks else 0
            ),
            "min_chunk_size": min((c.char_count for c in chunks), default=0),
            "max_chunk_size": max((c.char_count for c in chunks), default=0),
            "total_characters": sum(c.char_count for c in chunks),
        }
        logger.info(
            "Extraction done: %d chunks, avg size %d chars",
            self._stats["total_chunks"],
            int(self._stats["avg_chunk_size"]),
        )
        return chunks

    # ------------------------------------------------------------------

    def _detect_noise(self, pages_lines: List[List[str]]) -> set:
        """
        Return a set of lines that appear on many pages (likely headers/footers).
        Only considers short lines (< 40 chars after stripping).
        """
        total_pages = len(pages_lines)
        if total_pages < 3:
            return set()

        counter: Counter = Counter()
        for lines in pages_lines:
            seen_on_page: set = set()
            for line in lines:
                stripped = line.strip()
                if stripped and len(stripped) < 40:
                    seen_on_page.add(stripped)
            counter.update(seen_on_page)

        threshold = max(3, total_pages // 10)
        return {line for line, count in counter.items() if count >= threshold}

    def _is_chapter_heading(self, line: str) -> bool:
        if self._CHAPTER_RE.match(line):
            return True
        return False

    @staticmethod
    def _is_standalone_number(line: str) -> bool:
        """Return True for bare page numbers like '42' or 'halaman 42'."""
        if re.fullmatch(r"\d{1,4}", line):
            return True
        if re.fullmatch(r"(halaman|hal\.?|page)\s*\d{1,4}", line, re.IGNORECASE):
            return True
        return False

    def _build_chunks(
        self, raw_chunks: List[tuple[str, List[str], int, int]]
    ) -> List[ExtractionChunk]:
        chunks: List[ExtractionChunk] = []
        seen_titles: set = set()

        for title, lines, start, end in raw_chunks:
            # Skip duplicate chapter titles
            norm_title = title.strip().upper()
            if norm_title and norm_title in seen_titles:
                continue
            if norm_title:
                seen_titles.add(norm_title)

            content = self._clean_content(lines)
            if not content:
                continue
            chunk = ExtractionChunk.from_raw(
                title=title or f"Bagian {len(chunks) + 1}",
                content=content,
                start_page=start + 1,  # 1-indexed for users
                end_page=end + 1,
            )
            chunks.append(chunk)

        return chunks

    @staticmethod
    def _clean_content(lines: List[str]) -> str:
        """Join lines, normalize whitespace, remove excessive blank lines."""
        text = "\n".join(lines)
        # Collapse runs of 3+ newlines to 2
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Normalize other whitespace
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    def _merge_small_chunks(self, chunks: List[ExtractionChunk]) -> List[ExtractionChunk]:
        """Merge chunks that are below min_chunk_size into their predecessor."""
        if not chunks:
            return chunks

        merged: List[ExtractionChunk] = [chunks[0]]
        for chunk in chunks[1:]:
            prev = merged[-1]
            if chunk.char_count < self.min_chunk_size:
                # Append current chunk content to previous
                combined_content = prev.content + "\n\n" + chunk.content
                merged[-1] = ExtractionChunk.from_raw(
                    title=prev.title,
                    content=combined_content,
                    start_page=prev.start_page,
                    end_page=chunk.end_page,
                )
            else:
                merged.append(chunk)

        return merged

    def _split_large_chunks(self, chunks: List[ExtractionChunk]) -> List[ExtractionChunk]:
        """Split any chunk exceeding max_chunk_size into sub-chunks."""
        result: List[ExtractionChunk] = []
        for chunk in chunks:
            if chunk.char_count <= self.max_chunk_size:
                result.append(chunk)
                continue

            # Split on paragraph boundaries
            paragraphs = re.split(r"\n\n+", chunk.content)
            sub_content: List[str] = []
            sub_index = 1

            for para in paragraphs:
                sub_content.append(para)
                current = "\n\n".join(sub_content)
                if len(current) >= self.max_chunk_size:
                    result.append(
                        ExtractionChunk.from_raw(
                            title=f"{chunk.title} (bagian {sub_index})",
                            content=current.strip(),
                            start_page=chunk.start_page,
                            end_page=chunk.end_page,
                        )
                    )
                    sub_content = []
                    sub_index += 1

            if sub_content:
                remaining = "\n\n".join(sub_content).strip()
                if remaining:
                    result.append(
                        ExtractionChunk.from_raw(
                            title=f"{chunk.title} (bagian {sub_index})",
                            content=remaining,
                            start_page=chunk.start_page,
                            end_page=chunk.end_page,
                        )
                    )

        return result
