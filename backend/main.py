import asyncio
import sys
import os
import time
import warnings
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

# Suppress DeprecationWarnings for better terminal readability
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Load environment variables from .env file
load_dotenv()

# FIX: Force ProactorEventLoop on Windows for Playwright/Subprocess support
if sys.platform == 'win32':
    try:
        # Standard in Python 3.8+, but some Celery/Playwright versions still prefer explicit setting
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select, update, func
from routers import scrape, articles, diagnostics, brands, auth
from db.database import init_db, get_db, ScrapeJob, Article
import logging

# Standardized Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("API")

# Environment Validation
REQUIRED_ENV = ["DATABASE_URL", "REDIS_URL"]
missing = [env for env in REQUIRED_ENV if not os.getenv(env)]
if missing:
    logger.critical(f"FATAL: Missing required environment variables: {', '.join(missing)}")
    if os.getenv("STRICT_ENV", "false").lower() == "true":
        sys.exit(1)

app = FastAPI(
    title="NEXUS Intelligence",
    version="6.0.0",
)

@app.middleware("http")
async def global_exception_handler(request: Request, call_next):
    # Log all requests for debugging
    logger.info(f"REQUEST: {request.method} {request.url.path}")
    try:
        return await call_next(request)
    except Exception as e:
        logger.error(f"UNHANDLED ERROR: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error. The NEXUS team has been notified."}
        )

# CORS
_raw_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost:3000"
)
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "fallback_secret_key_nexus_6000"),
)

def handle_loop_exception(loop, context):
    exception = context.get("exception")
    # Suppress WinError 10054 noise on Windows (ConnectionResetError)
    if isinstance(exception, ConnectionResetError) or (exception and "[WinError 10054]" in str(exception)):
        return
    loop.default_exception_handler(context)

@app.on_event("startup")
async def startup_event():
    # Set the exception handler for the loop to silent Windows socket noise
    try:
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(handle_loop_exception)
    except Exception: pass

    # Initialize DB (Alembic is better, but this handles simple runs)
    try:
        await init_db()
    except Exception as e:
        print(f"DB Init Error (likely connection): {e}")
    
    print(f"API started. CORS origins: {ALLOWED_ORIGINS}")

@app.on_event("startup")
async def recover_stuck_jobs():
    """Mark interrupted jobs on startup."""
    try:
        async with get_db() as db:
            stmt = (
                update(ScrapeJob)
                .where(ScrapeJob.status.in_(['running', 'pending']))
                .values(status='interrupted', error='Server restarted')
            )
            await db.execute(stmt)
            await db.commit()
    except Exception as e:
        print(f"Recovery Error: {e}")

@app.on_event("startup")
async def start_scheduler():
    """Daily 3 AM Scrape."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from celery_app import celery_app
    from scraper.config import SECTOR_KEYWORDS
    
    scheduler = AsyncIOScheduler()

    async def scheduled_job():
        yesterday = date.today() - timedelta(days=1)
        for sector in SECTOR_KEYWORDS.keys():
            # Trigger via Celery (distributed)
            import uuid
            job_id = str(uuid.uuid4())
            # We need to save the job row first? 
            # Actually, simpler to just dispatch the task which handles its own DB state if needed.
            # But run_scrape_task expects a job_id in DB.
            async with get_db() as db:
                new_job = ScrapeJob(
                    id=job_id, sector=sector, region="india", user_id="system",
                    date_from=yesterday, date_to=yesterday, status='pending'
                )
                db.add(new_job)
                await db.commit()
            
            celery_app.send_task(
                "scraper.tasks.run_scrape_task",
                args=[job_id, sector, "india", str(yesterday), str(yesterday), "broad", "system"]
            )

    scheduler.add_job(scheduled_job, CronTrigger(hour=3, minute=0))
    scheduler.start()

# Include Routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(scrape.router, prefix="/api/scrape", tags=["scraping"])
app.include_router(articles.router, prefix="/api/articles", tags=["articles"])
app.include_router(diagnostics.router, prefix="/api/diagnostics", tags=["diagnostics"])
app.include_router(brands.router, prefix="/api/brands", tags=["brands"])

@app.get("/")
def root():
    return {"status": "Crexito Scrape Distributed API is running", "version": "6.0.0"}

@app.get("/health")
async def health():
    """Enterprise Health Check (D-3)."""
    try:
        from scraper.engine import get_browser_instance, get_redis
        
        # 1. Check DB
        db_start = time.time()
        async with get_db() as db:
            res = await db.execute(select(func.count(Article.id)))
            count = res.scalar()
        db_ms = int((time.time() - db_start) * 1000)

        # 2. Check Redis
        redis_start = time.time()
        r = await get_redis()
        await r.ping()
        redis_ms = int((time.time() - redis_start) * 1000)

        # 3. Warm-up Browser
        browser_start = time.time()
        browser = await get_browser_instance()
        browser_ok = browser is not None and browser.is_connected()
        browser_ms = int((time.time() - browser_start) * 1000)

        return {
            "status": "healthy" if browser_ok else "degraded",
            "uptime": "TODO", # Add uptime logic if needed
            "total_articles": count,
            "latency_ms": {
                "database": db_ms,
                "redis": redis_ms,
                "browser": browser_ms
            },
            "services": {
                "redis": "connected",
                "browser": "ready" if browser_ok else "failed"
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )
