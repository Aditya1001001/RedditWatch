"""Database setup and session management for RedditWatch."""

import sys
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# Database path
DATA_DIR = Path(__file__).parent.parent.parent / "data"
DATABASE_PATH = DATA_DIR / "redditwatch.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_PATH}"


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL debugging
    future=True,
)

# Session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database sessions."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Initialize the database, creating all tables."""
    # Ensure data directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Import models to register them with Base
    from app.models import audience, comment, insight, post, subscriber_snapshot, subreddit, theme  # noqa: F401

    async with engine.begin() as conn:
        # Enable foreign keys for SQLite
        await conn.execute(text("PRAGMA foreign_keys = ON"))

        # Create all tables
        await conn.run_sync(Base.metadata.create_all)

        # Add columns that may not exist in older databases
        try:
            await conn.execute(text(
                "ALTER TABLE monitored_subreddits ADD COLUMN icon_url VARCHAR(500)"
            ))
        except Exception:
            pass  # Column already exists

    print(f"Database initialized at {DATABASE_PATH}")


async def drop_db() -> None:
    """Drop all tables (use with caution!)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    print("All tables dropped")


# CLI for database management
if __name__ == "__main__":
    import asyncio

    if len(sys.argv) < 2:
        print("Usage: python -m app.database [init|drop]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "init":
        asyncio.run(init_db())
    elif command == "drop":
        confirm = input("This will delete all data. Are you sure? (yes/no): ")
        if confirm.lower() == "yes":
            asyncio.run(drop_db())
        else:
            print("Aborted")
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
