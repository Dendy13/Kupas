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


# DDL statements to apply when upgrading an existing schema.
# Using literal strings (no user input) to avoid any injection risk.
_MIGRATIONS = [
    "ALTER TABLE books ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();",
    "ALTER TABLE books ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();",
    "ALTER TABLE job_logs ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();",
    "ALTER TABLE job_logs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();",
    "ALTER TABLE books ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE;",
    "ALTER TABLE books ALTER COLUMN updated_at TYPE TIMESTAMP WITH TIME ZONE;",
]


async def upgrade_schema() -> None:
    """Add any missing columns to existing tables (idempotent)."""
    async with engine.begin() as conn:
        for stmt in _MIGRATIONS:
            await conn.execute(text(stmt))


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await upgrade_schema()


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        yield session
