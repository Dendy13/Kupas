"""
kupas/models.py
Single source of truth for all SQLAlchemy ORM models.
"""

from datetime import datetime, timezone
from sqlalchemy import DateTime, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    chapters: Mapped[list["Chapter"]] = relationship(
        "Chapter", back_populates="book", cascade="all, delete-orphan"
    )
    generated_content: Mapped["GeneratedContent | None"] = relationship(
        "GeneratedContent", back_populates="book", cascade="all, delete-orphan", uselist=False
    )


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), index=True)
    chapter_number: Mapped[int]
    title: Mapped[str | None]
    content: Mapped[str | None] = mapped_column(Text)
    book: Mapped["Book"] = relationship("Book", back_populates="chapters")


class GeneratedContent(Base):
    """Cache for AI-generated summaries and questions. One row per book."""
    __tablename__ = "generated_content"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), unique=True, index=True)
    summary: Mapped[str] = mapped_column(Text)
    questions_json: Mapped[str] = mapped_column(Text)  # JSON array string
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    book: Mapped["Book"] = relationship("Book", back_populates="generated_content")


class ExtractionSession(Base):
    """Tracks one PDF extraction run for a book."""
    __tablename__ = "extraction_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), index=True)
    status: Mapped[str] = mapped_column(default="draft")  # draft | in_review | approved | rejected
    total_pages: Mapped[int | None]
    total_chunks: Mapped[int | None]
    approved_by: Mapped[int | None]
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    book: Mapped["Book"] = relationship("Book")
    chunks: Mapped[list["ExtractionChunk"]] = relationship(
        "ExtractionChunk", back_populates="session", cascade="all, delete-orphan",
        order_by="ExtractionChunk.order_index",
    )


class ExtractionChunk(Base):
    """A single verified content chunk from an extraction session."""
    __tablename__ = "extraction_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("extraction_sessions.id"), index=True)
    title: Mapped[str | None]
    content: Mapped[str | None] = mapped_column(Text)
    start_page: Mapped[int | None]
    end_page: Mapped[int | None]
    char_count: Mapped[int | None]
    word_count: Mapped[int | None]
    quality_score: Mapped[float | None]
    is_verified: Mapped[bool] = mapped_column(default=False)
    verified_by: Mapped[int | None]
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    order_index: Mapped[int] = mapped_column(default=0)
    session: Mapped["ExtractionSession"] = relationship("ExtractionSession", back_populates="chunks")


class JobLog(Base):
    """Tracks background job execution status."""
    __tablename__ = "job_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_type: Mapped[str]          # "fetch_catalog", "download_pdf",
                                   # "extract_text", "generate_ai"
    slug: Mapped[str | None]       # None = bulk job
    status: Mapped[str]            # "pending", "running", "done", "error"
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
