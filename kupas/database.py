"""
kupas/database.py
Single engine and session factory for the whole application.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from kupas.config import DATABASE_URL
from kupas.models import Base

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False)


# Columns that were added to existing models after the initial schema was created.
# Each entry is (table, column, column_definition).
_MIGRATIONS = [
    ("books", "created_at", "TIMESTAMP DEFAULT NOW()"),
    ("books", "updated_at", "TIMESTAMP DEFAULT NOW()"),
    ("job_logs", "created_at", "TIMESTAMP DEFAULT NOW()"),
    ("job_logs", "updated_at", "TIMESTAMP DEFAULT NOW()"),
]


async def upgrade_schema() -> None:
    """Add any missing columns to existing tables (idempotent)."""
    async with engine.begin() as conn:
        for table, column, definition in _MIGRATIONS:
            await conn.execute(
                text(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {definition};"
                )
            )


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await upgrade_schema()


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        yield session
