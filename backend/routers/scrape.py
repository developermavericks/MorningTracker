import uuid
import asyncio
from datetime import date, datetime
from typing import List
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select, func, update, delete
from db.database import get_db, ScrapeJob, Article, User
from .auth_utils import get_auth_user as get_current_user, TokenData
from celery_app import app as celery_app
from scraper.config import REGION_MAP, SECTOR_KEYWORDS
from scraper.engine import log

router = APIRouter()

class ScrapeRequest(BaseModel):
    sector: str
    region: str
    date_from: date
    date_to: date
    search_mode: str = "broad"

@router.post("/start")
async def start_scrape(req: ScrapeRequest, current_user: TokenData = Depends(get_current_user)):
    """Kick off a new scrape job using Celery."""
    # Validation
    if req.sector.lower() not in SECTOR_KEYWORDS:
        raise HTTPException(400, f"Unknown sector.")
    if req.region.lower() not in REGION_MAP:
        raise HTTPException(400, f"Unknown region.")
    if req.date_from > req.date_to:
        raise HTTPException(400, "Invalid date range.")

    date_span = (req.date_to - req.date_from).days
    if date_span > 30:
        raise HTTPException(400, "Date range exceeds 30-day limit.")

    async with get_db() as db:
        # Check active jobs
        res = await db.execute(
            select(func.count(ScrapeJob.id))
            .where(ScrapeJob.user_id == current_user.id)
            .where(ScrapeJob.status.in_(['running', 'pending']))
        )
        already_running = res.scalar()
        if already_running >= 2:
            raise HTTPException(409, f"User has {already_running} active jobs. Limit is 2.")

        job_id = str(uuid.uuid4())
        new_job = ScrapeJob(
            id=job_id,
            sector=req.sector.lower(),
            region=req.region.lower(),
            user_id=current_user.id,
            date_from=req.date_from,
            date_to=req.date_to,
            status='pending',
            search_mode=req.search_mode,
            started_at=datetime.now()
        )
        db.add(new_job)
        await db.commit()

    # Dispatch to Celery
    celery_app.send_task(
        "scraper.tasks.run_scrape_task",
        args=[job_id, req.sector.lower(), req.region.lower(), str(req.date_from), str(req.date_to), req.search_mode, current_user.id]
    )

    return {"job_id": job_id, "status": "pending"}

@router.post("/enrich")
async def start_enrichment(current_user: TokenData = Depends(get_current_user)):
    """Triggers enrichment for articles with missing content."""
    # Moved to Celery for distributed processing
    from scraper.tasks import enrich_article_node
    
    async with get_db() as db:
        # Find articles needing enrichment (Scoped to current user)
        stmt = select(Article.id).where(
            Article.user_id == current_user.id,
            (Article.full_body == None) | (func.length(Article.full_body) < 150)
        ).limit(1000)
        res = await db.execute(stmt)
        ids = res.scalars().all()
        
        for art_id in ids:
            enrich_article_node.delay(art_id)
            
    return {"status": "enqueued", "count": len(ids)}

@router.get("/jobs")
async def list_jobs(limit: int = 20, current_user: TokenData = Depends(get_current_user)):
    """List recent scrape jobs for current user (or all if admin)."""
    async with get_db() as db:
        # Join with User to get initiator info
        stmt = select(ScrapeJob, User.name, User.email).join(User, ScrapeJob.user_id == User.id, isouter=True)
        
        if not current_user.is_admin:
            stmt = stmt.where(ScrapeJob.user_id == current_user.id)
            
        res = await db.execute(
            stmt.order_by(ScrapeJob.started_at.desc()).limit(limit)
        )
        rows = res.all()
        
        jobs = []
        for row in rows:
            job, user_name, user_email = row
            job_dict = {c.name: getattr(job, c.name) for c in job.__table__.columns}
            job_dict["user_name"] = user_name or "System/Unknown"
            job_dict["user_email"] = user_email or "N/A"
            jobs.append(job_dict)
            
        return jobs

@router.get("/job/{job_id}")
async def get_job_status(job_id: str, current_user: TokenData = Depends(get_current_user)):
    """Get status and progress of a scrape job."""
    async with get_db() as db:
        stmt = select(ScrapeJob).where(ScrapeJob.id == job_id)
        if not current_user.is_admin:
            stmt = stmt.where(ScrapeJob.user_id == current_user.id)
            
        res = await db.execute(stmt)
        job = res.scalar_one_or_none()
        if not job:
            raise HTTPException(404, "Job not found or access denied")
        return job

@router.delete("/job/{job_id}")
async def delete_job(job_id: str, current_user: TokenData = Depends(get_current_user)):
    """Delete a job and its articles."""
    async with get_db() as db:
        stmt = select(ScrapeJob).where(ScrapeJob.id == job_id)
        if not current_user.is_admin:
            stmt = stmt.where(ScrapeJob.user_id == current_user.id)
            
        res = await db.execute(stmt)
        job = res.scalar_one_or_none()
        if not job:
            raise HTTPException(404, "Job not found or access denied")
        
        # C-X: Signal cancellation to workers via Redis
        from scraper.llm import get_redis
        try:
            r = await get_redis()
            await r.sadd("nexus:cancelled_jobs", job_id)
            await r.expire("nexus:cancelled_jobs", 86400) # 24h cleanup
        except:
            pass
            
        await db.execute(delete(Article).where(Article.scrape_job_id == job_id))
        await db.delete(job)
        await db.commit()
    return {"deleted": job_id}

@router.get("/options")
def get_options():
    """Return available sectors and regions."""
    return {
        "sectors": sorted(SECTOR_KEYWORDS.keys()),
        "regions": sorted(REGION_MAP.keys()),
    }
