import os
import json
from datetime import datetime, date
from typing import Optional, List, Any, Dict
from contextlib import asynccontextmanager

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Date, Float, ForeignKey, Index, select, update, delete, Table, JSON, create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

# ─── Configuration ──────────────────────────────────────────────────────────

def get_database_url():
    url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///news_scraper.db")
    if url:
        # Strip whitespace and trailing newlines
        url = url.strip()
        # Strip leading/trailing quotes if present
        url = url.strip("\"'")
        # If the user copy-pasted a comment after the URL, extract only the URL part
        if " " in url:
            url = url.split()[0]
            url = url.strip("\"'")
            
    # Check for empty or unresolved template string
    if not url or url.startswith("${{"):
        print(f"NEXUS DB WARNING: DATABASE_URL is empty or unresolved template: '{url}'. Falling back to local SQLite.")
        url = "sqlite+aiosqlite:///news_scraper.db"
        
    # Check for valid schemes
    if not (url.startswith("postgresql") or url.startswith("sqlite")):
        print(f"NEXUS DB WARNING: DATABASE_URL has invalid scheme: '{url[:30]}...'. Falling back to local SQLite.")
        url = "sqlite+aiosqlite:///news_scraper.db"
        
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
elif "sqlite" not in get_database_url():
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
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

class Article(Base):
    __tablename__ = "articles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
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
        Index("idx_unique_url_user", "url", "user_id", unique=True),
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

    __table_args__ = (
        Index("idx_scrape_jobs_started_at", "started_at"),
        Index("idx_scrape_jobs_sector", "sector"),
        Index("idx_scrape_jobs_user_id", "user_id"),
    )

class WatchedBrand(Base):
    __tablename__ = "watched_brands"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    keywords: Mapped[Optional[str]] = mapped_column(Text)
    region: Mapped[str] = mapped_column(String, default="india")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    last_scraped: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    __table_args__ = (
        Index("idx_unique_brand_user", "name", "user_id", unique=True),
    )

class Client(Base):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    scheduled_time: Mapped[str] = mapped_column(String, default="07:00")
    timezone: Mapped[str] = mapped_column(String, default="Asia/Kolkata")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    template_path: Mapped[Optional[str]] = mapped_column(String)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    context: Mapped[Optional[str]] = mapped_column(Text)

class ClientSection(Base):
    __tablename__ = "client_sections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)

class ClientKeyword(Base):
    __tablename__ = "client_keywords"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    section_id: Mapped[int] = mapped_column(Integer, ForeignKey("client_sections.id", ondelete="CASCADE"), nullable=False)
    keyword: Mapped[str] = mapped_column(String, nullable=False)

class ClientRecipient(Base):
    __tablename__ = "client_recipients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)

class ClientRunLog(Base):
    __tablename__ = "client_run_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")  # running, completed, failed
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    progress_message: Mapped[Optional[str]] = mapped_column(Text)
    generated_file_path: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

class SystemSetting(Base):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)

class IrrelevantArticle(Base):
    __tablename__ = "irrelevant_articles"
    url: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    relevance_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

class JobFunnelLog(Base):
    __tablename__ = "job_funnel_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String, index=True)
    rss_discovered: Mapped[int] = mapped_column(Integer, default=0)
    cache_skipped: Mapped[int] = mapped_column(Integer, default=0)
    pre_filter_dropped: Mapped[int] = mapped_column(Integer, default=0)
    scraped_count: Mapped[int] = mapped_column(Integer, default=0)
    relevance_yes: Mapped[int] = mapped_column(Integer, default=0)
    relevance_no: Mapped[int] = mapped_column(Integer, default=0)
    summarized_count: Mapped[int] = mapped_column(Integer, default=0)
    fallback_count: Mapped[int] = mapped_column(Integer, default=0)
    logged_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
class ZeroResultQuery(Base):
    __tablename__ = "zero_result_queries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_string: Mapped[str] = mapped_column(String, index=True)
    sector: Mapped[str] = mapped_column(String, index=True)
    count: Mapped[int] = mapped_column(Integer, default=1)
    logged_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

class DirectFeed(Base):
    __tablename__ = "direct_feeds"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    publication_name: Mapped[str] = mapped_column(String, nullable=False)
    feed_url: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String, default="A")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

# ─── Initialization ───────────────────────────────────────────────────────────

async def init_db():
    async with engine.begin() as conn:
        # For professional deployment, Alembic is preferred.
        # This ensures tables exist on first run.
        await conn.run_sync(Base.metadata.create_all)
        
        # Automated Migration: Article Multi-tenancy (Drop old URL unique constraint)
        try:
            if "postgresql" in engine.url.drivername:
                # PostgreSQL creates a constraint called 'articles_url_key' for unique=True
                await conn.execute(text("ALTER TABLE articles DROP CONSTRAINT IF EXISTS articles_url_key"))
                # Also ensure the new composite index exists (if create_all didn't catch it)
                await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_url_user ON articles (url, user_id)"))
            else:
                # SQLite - we manually create the index as a fallback
                await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_url_user ON articles (url, user_id)"))
        except Exception as e:
            print(f"Migration Notice (Article Schema): {e}")

        # Automated Migration: Add is_admin if missing
        try:
            if "postgresql" in engine.url.drivername:
                await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE"))
            else:
                await conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE"))
        except: pass

        # Automated Migration: Add audit columns to irrelevant_articles table
        try:
            if "postgresql" in engine.url.drivername:
                await conn.execute(text("ALTER TABLE irrelevant_articles ADD COLUMN IF NOT EXISTS title VARCHAR"))
                await conn.execute(text("ALTER TABLE irrelevant_articles ADD COLUMN IF NOT EXISTS description TEXT"))
                await conn.execute(text("ALTER TABLE irrelevant_articles ADD COLUMN IF NOT EXISTS rejection_reason TEXT"))
                await conn.execute(text("ALTER TABLE irrelevant_articles ADD COLUMN IF NOT EXISTS relevance_score FLOAT"))
            else:
                # SQLite - we execute ADD COLUMN individually inside try/except to tolerate column presence
                try:
                    await conn.execute(text("ALTER TABLE irrelevant_articles ADD COLUMN title VARCHAR"))
                except Exception: pass
                try:
                    await conn.execute(text("ALTER TABLE irrelevant_articles ADD COLUMN description TEXT"))
                except Exception: pass
                try:
                    await conn.execute(text("ALTER TABLE irrelevant_articles ADD COLUMN rejection_reason TEXT"))
                except Exception: pass
                try:
                    await conn.execute(text("ALTER TABLE irrelevant_articles ADD COLUMN relevance_score FLOAT"))
                except Exception: pass
        except Exception as e:
            print(f"Migration Notice (IrrelevantArticle Columns): {e}")

        # Automated Migration: Add logged_at to job_funnel_logs if missing
        try:
            if "postgresql" in engine.url.drivername:
                await conn.execute(text("ALTER TABLE job_funnel_logs ADD COLUMN IF NOT EXISTS logged_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()"))
            else:
                try:
                    await conn.execute(text("ALTER TABLE job_funnel_logs ADD COLUMN logged_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
                except Exception: pass
        except Exception as e:
            print(f"Migration Notice (JobFunnelLog logged_at): {e}")

        # Automated Migration: Add progress_message if missing
        try:
            if "postgresql" in engine.url.drivername:
                await conn.execute(text("ALTER TABLE client_run_logs ADD COLUMN IF NOT EXISTS progress_message TEXT"))
            else:
                await conn.execute(text("ALTER TABLE client_run_logs ADD COLUMN progress_message TEXT"))
        except: pass

        # Automated Migration: Add client context if missing
        try:
            if "postgresql" in engine.url.drivername:
                await conn.execute(text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS context TEXT"))
            else:
                await conn.execute(text("ALTER TABLE clients ADD COLUMN context TEXT"))
        except: pass

        # Automated Cleanup: Duplicate Brands
        try:
            # We use a raw SQL approach for broad compatibility
            res = await conn.execute(text("""
                SELECT name, user_id, COUNT(*) 
                FROM watched_brands 
                GROUP BY name, user_id 
                HAVING COUNT(*) > 1
            """))
            duplicates = res.all()
            for name, user_id, count in duplicates:
                # Find all records for this duplicate pair
                res_all = await conn.execute(text(
                    "SELECT id FROM watched_brands WHERE name = :name AND user_id = :user_id ORDER BY id ASC"
                ), {"name": name, "user_id": user_id})
                ids = [r[0] for r in res_all.all()]
                
                # Keep the first one, rename the rest
                for i, brand_id in enumerate(ids[1:], start=1):
                    new_name = f"{name} {i}"
                    await conn.execute(text(
                        "UPDATE watched_brands SET name = :new_name WHERE id = :id"
                    ), {"new_name": new_name, "id": brand_id})
                    print(f"Migration: Renamed duplicate brand '{name}' to '{new_name}' (User: {user_id})")
        except Exception as e:
            print(f"Migration Notice (Brand Cleanup): {e}")

        # Seed default feeds if empty
        try:
            feed_count = (await conn.execute(text("SELECT COUNT(*) FROM direct_feeds"))).scalar()
            if feed_count == 0:
                default_feeds = [
                    {"publication_name": "Reuters", "feed_url": "https://news.google.com/rss/search?q=source:Reuters", "category": "A", "is_active": True},
                    {"publication_name": "Bloomberg", "feed_url": "https://news.google.com/rss/search?q=source:Bloomberg", "category": "A", "is_active": True},
                    {"publication_name": "The Economic Times", "feed_url": "https://economictimes.indiatimes.com/rssfeedstopstories.cms", "category": "A", "is_active": True},
                    {"publication_name": "Livemint", "feed_url": "https://www.livemint.com/rss/news", "category": "A", "is_active": True},
                    {"publication_name": "The Hindu", "feed_url": "https://www.thehindu.com/feeder/default.rss", "category": "A", "is_active": True},
                    {"publication_name": "The Times of India", "feed_url": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms", "category": "A", "is_active": True},
                    {"publication_name": "The Indian Express", "feed_url": "https://news.google.com/rss/search?q=source:%22The%20Indian%20Express%22", "category": "A", "is_active": True},
                    {"publication_name": "Moneycontrol", "feed_url": "https://www.moneycontrol.com/rss/latestnews.xml", "category": "A", "is_active": True}
                ]
                for f in default_feeds:
                    await conn.execute(text(
                        "INSERT INTO direct_feeds (publication_name, feed_url, category, is_active, created_at) "
                        "VALUES (:publication_name, :feed_url, :category, :is_active, :created_at)"
                    ), {**f, "created_at": datetime.now()})
                print("Database: Seeded default direct feeds.")
        except Exception as seed_err:
            print(f"Migration Notice (Seed Direct Feeds): {seed_err}")
                
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
    # Automated migration: Add client context if missing
    try:
        with engine_sync.begin() as conn:
            if "postgresql" in engine_sync.url.drivername:
                conn.execute(text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS context TEXT"))
            else:
                conn.execute(text("ALTER TABLE clients ADD COLUMN context TEXT"))
    except: pass

    # Automated migration: Add audit columns to irrelevant_articles table
    try:
        with engine_sync.begin() as conn:
            if "postgresql" in engine_sync.url.drivername:
                conn.execute(text("ALTER TABLE irrelevant_articles ADD COLUMN IF NOT EXISTS title VARCHAR"))
                conn.execute(text("ALTER TABLE irrelevant_articles ADD COLUMN IF NOT EXISTS description TEXT"))
                conn.execute(text("ALTER TABLE irrelevant_articles ADD COLUMN IF NOT EXISTS rejection_reason TEXT"))
                conn.execute(text("ALTER TABLE irrelevant_articles ADD COLUMN IF NOT EXISTS relevance_score FLOAT"))
            else:
                try:
                    conn.execute(text("ALTER TABLE irrelevant_articles ADD COLUMN title VARCHAR"))
                except Exception: pass
                try:
                    conn.execute(text("ALTER TABLE irrelevant_articles ADD COLUMN description TEXT"))
                except Exception: pass
                try:
                    conn.execute(text("ALTER TABLE irrelevant_articles ADD COLUMN rejection_reason TEXT"))
                except Exception: pass
                try:
                    conn.execute(text("ALTER TABLE irrelevant_articles ADD COLUMN relevance_score FLOAT"))
                except Exception: pass
    except: pass

    # Automated migration: Add logged_at to job_funnel_logs if missing
    try:
        with engine_sync.begin() as conn:
            if "postgresql" in engine_sync.url.drivername:
                conn.execute(text("ALTER TABLE job_funnel_logs ADD COLUMN IF NOT EXISTS logged_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()"))
            else:
                try:
                    conn.execute(text("ALTER TABLE job_funnel_logs ADD COLUMN logged_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
                except Exception: pass
    except: pass
    # Automated migration: Add direct_feeds table and seed default feeds if empty
    try:
        with engine_sync.begin() as conn:
            # Create direct_feeds table if it doesn't exist
            if "postgresql" in engine_sync.url.drivername:
                conn.execute(text(
                    "CREATE TABLE IF NOT EXISTS direct_feeds ("
                    "id SERIAL PRIMARY KEY, "
                    "publication_name VARCHAR NOT NULL, "
                    "feed_url VARCHAR UNIQUE NOT NULL, "
                    "category VARCHAR DEFAULT 'A', "
                    "is_active BOOLEAN DEFAULT TRUE, "
                    "created_at TIMESTAMP WITHOUT TIME ZONE"
                    ")"
                ))
            else:
                conn.execute(text(
                    "CREATE TABLE IF NOT EXISTS direct_feeds ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "publication_name VARCHAR NOT NULL, "
                    "feed_url VARCHAR UNIQUE NOT NULL, "
                    "category VARCHAR DEFAULT 'A', "
                    "is_active BOOLEAN DEFAULT 1, "
                    "created_at DATETIME"
                    ")"
                ))
            # Seed default feeds if empty
            feed_count = conn.execute(text("SELECT COUNT(*) FROM direct_feeds")).scalar()
            if feed_count == 0:
                default_feeds = [
                    {"publication_name": "Reuters", "feed_url": "https://news.google.com/rss/search?q=source:Reuters", "category": "A", "is_active": True},
                    {"publication_name": "Bloomberg", "feed_url": "https://news.google.com/rss/search?q=source:Bloomberg", "category": "A", "is_active": True},
                    {"publication_name": "The Economic Times", "feed_url": "https://economictimes.indiatimes.com/rssfeedstopstories.cms", "category": "A", "is_active": True},
                    {"publication_name": "Livemint", "feed_url": "https://www.livemint.com/rss/news", "category": "A", "is_active": True},
                    {"publication_name": "The Hindu", "feed_url": "https://www.thehindu.com/feeder/default.rss", "category": "A", "is_active": True},
                    {"publication_name": "The Times of India", "feed_url": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms", "category": "A", "is_active": True},
                    {"publication_name": "The Indian Express", "feed_url": "https://news.google.com/rss/search?q=source:%22The%20Indian%20Express%22", "category": "A", "is_active": True},
                    {"publication_name": "Moneycontrol", "feed_url": "https://www.moneycontrol.com/rss/latestnews.xml", "category": "A", "is_active": True}
                ]
                for f in default_feeds:
                    conn.execute(text(
                        "INSERT INTO direct_feeds (publication_name, feed_url, category, is_active, created_at) "
                        "VALUES (:publication_name, :feed_url, :category, :is_active, :created_at)"
                    ), {**f, "created_at": datetime.now()})
                print("Sync Database: Seeded default direct feeds.")
    except Exception as e:
        print(f"Sync Migration Notice (Direct Feeds): {e}")

    print(f"Sync Database initialized via SQLAlchemy ({engine_sync.url.drivername})")

# Connection Lifecycle is handled via get_db and SessionMiddleware
