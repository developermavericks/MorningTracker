import os
import json
from datetime import datetime, date
from typing import Optional, List, Any, Dict
from contextlib import asynccontextmanager

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Date, Float, ForeignKey, Index, select, update, delete, Table, JSON, create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

# ─── Configuration ──────────────────────────────────────────────────────────

def get_database_url():
    url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///news_scraper.db")
    # SQLAlchemy requires +asyncpg for postgres
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://")
    return url

from sqlalchemy.pool import NullPool, QueuePool

# Selective Pooling: Use NullPool for workers to prevent gevent/asyncpg lifecycle conflicts.
# The user's log analysis highlighted that asyncpg termination fails when many workers share a pool.
use_nullpool = os.getenv("DB_USE_NULLPOOL", "false").lower() == "true"

engine_args = {
    "echo": False,
    "pool_pre_ping": True,
}

if use_nullpool:
    engine_args["poolclass"] = NullPool
else:
    engine_args.update({
        "pool_size": int(os.getenv("DB_POOL_SIZE", "20")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "60")),
        "pool_recycle": 3600,
    })

async_connect_args = {"timeout": 60} if "sqlite" in get_database_url() else {"command_timeout": 60}
engine = create_async_engine(get_database_url(), connect_args=async_connect_args, **engine_args)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# Synchronous Engine for Workers
def get_sync_url():
    url = get_database_url()
    return url.replace("+aiosqlite", "").replace("+asyncpg", "")

sync_connect_args = {"timeout": 60} if "sqlite" in get_sync_url() else {"connect_timeout": 60}
engine_sync = create_engine(get_sync_url(), connect_args=sync_connect_args, **engine_args)
SessionLocalSync = sessionmaker(bind=engine_sync, expire_on_commit=False)

# ─── Models ──────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String)
    hashed_password: Mapped[Optional[str]] = mapped_column(String)
    google_id: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class Article(Base):
    __tablename__ = "articles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    resolved_url: Mapped[Optional[str]] = mapped_column(Text)
    full_body: Mapped[Optional[str]] = mapped_column(Text)
    author: Mapped[Optional[str]] = mapped_column(String)
    agency: Mapped[Optional[str]] = mapped_column(String)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    sector: Mapped[str] = mapped_column(String, nullable=False)
    region: Mapped[str] = mapped_column(String, nullable=False)
    language: Mapped[str] = mapped_column(String, default="en")
    source_feed: Mapped[Optional[str]] = mapped_column(String)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    scrape_job_id: Mapped[Optional[str]] = mapped_column(String, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String, index=True)
    word_count: Mapped[Optional[int]] = mapped_column(Integer)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    sentiment: Mapped[Optional[str]] = mapped_column(String)
    tags: Mapped[Optional[str]] = mapped_column(Text)
    title_hash: Mapped[Optional[str]] = mapped_column(String, index=True)
    
    # Industrial-grade Metadata Storage (Agnostic JSON)
    extra_metadata: Mapped[dict] = mapped_column(JSON, default={}, nullable=False)

    __table_args__ = (
        Index("idx_articles_sector", "sector"),
        Index("idx_articles_region", "region"),
        Index("idx_articles_published_at", "published_at"),
    )

class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    sector: Mapped[str] = mapped_column(String, nullable=False)
    region: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(String, index=True)
    date_from: Mapped[date] = mapped_column(Date, nullable=False)
    date_to: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")
    total_found: Mapped[int] = mapped_column(Integer, default=0)
    total_scraped: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    error: Mapped[Optional[str]] = mapped_column(Text)
    search_mode: Mapped[str] = mapped_column(String, default="broad")
    cumulative_found: Mapped[int] = mapped_column(Integer, default=0)
    current_phase: Mapped[str] = mapped_column(String, default="Preflight")
    phase_stats: Mapped[Optional[str]] = mapped_column(Text) # JSON string

class WatchedBrand(Base):
    __tablename__ = "watched_brands"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    keywords: Mapped[Optional[str]] = mapped_column(Text)
    region: Mapped[str] = mapped_column(String, default="india")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    last_scraped: Mapped[Optional[datetime]] = mapped_column(DateTime)

# ─── Initialization ───────────────────────────────────────────────────────────

async def init_db():
    async with engine.begin() as conn:
        # For professional deployment, Alembic is preferred.
        # This ensures tables exist on first run.
        await conn.run_sync(Base.metadata.create_all)
    print(f"Database initialized via SQLAlchemy ({engine.url.drivername})")

# ─── Connection Lifecycle ─────────────────────────────────────────────────────

@asynccontextmanager
async def get_db():
    """Context manager for 'async with get_db() as db' usage."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def get_db_yield():
    """FastAPI dependency wrapper for get_db."""
    async with get_db() as db:
        yield db

from contextlib import contextmanager

@contextmanager
def get_db_sync():
    """Synchronous context manager for gevent workers."""
    session = SessionLocalSync()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def init_db_sync():
    Base.metadata.create_all(bind=engine_sync)
    print(f"Sync Database initialized via SQLAlchemy ({engine_sync.url.drivername})")

# Connection Lifecycle is handled via get_db and SessionMiddleware
