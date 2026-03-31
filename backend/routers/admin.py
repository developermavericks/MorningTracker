from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
import datetime as dt
from datetime import date, datetime, time

from db.database import get_db_yield, ScrapeJob, User, Article, WatchedBrand
from .auth_utils import get_auth_user, TokenData

router = APIRouter(prefix="/admin", tags=["admin"])

async def get_admin_user(current_user: TokenData = Depends(get_auth_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

@router.get("/jobs")
async def list_all_jobs(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user_name: Optional[str] = None,
    user_email: Optional[str] = None,
    brand: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sort_by: str = "started_at",
    sort_order: str = "desc",
    db: AsyncSession = Depends(get_db_yield),
    _admin: TokenData = Depends(get_admin_user)
):
    # Base query with Join to User
    query = select(ScrapeJob, User.name, User.email).join(User, ScrapeJob.user_id == User.id, isouter=True)
    
    # Filters
    filters = []
    if user_name:
        filters.append(User.name.icontains(user_name))
    if user_email:
        filters.append(User.email.icontains(user_email))
    if brand:
        filters.append(ScrapeJob.sector.icontains(brand))
    if status:
        filters.append(ScrapeJob.status == status)
    
    # Robust Date Filtering
    try:
        if date_from:
            target_date = date_from
            if isinstance(target_date, str) and target_date.strip():
                target_date = dt.date.fromisoformat(target_date.split('T')[0])
            elif isinstance(target_date, dt.datetime):
                target_date = target_date.date()
                
            if isinstance(target_date, dt.date):
                filters.append(ScrapeJob.started_at >= dt.datetime.combine(target_date, dt.time.min))

        if date_to:
            target_date = date_to
            if isinstance(target_date, str) and target_date.strip():
                target_date = dt.date.fromisoformat(target_date.split('T')[0])
            elif isinstance(target_date, dt.datetime):
                target_date = target_date.date()
                
            if isinstance(target_date, dt.date):
                filters.append(ScrapeJob.started_at <= dt.datetime.combine(target_date, dt.time.max))
    except Exception:
        pass
    
    if filters:
        query = query.where(and_(*filters))
    
    # Sorting
    sort_attr = getattr(ScrapeJob, sort_by, ScrapeJob.started_at)
    if sort_order == "desc":
        query = query.order_by(desc(sort_attr))
    else:
        query = query.order_by(sort_attr)
    
    # Pagination
    offset = (page - 1) * limit
    
    # Count total for pagination
    count_query = select(func.count()).select_from(ScrapeJob).join(User, ScrapeJob.user_id == User.id, isouter=True)
    if filters:
        count_query = count_query.where(and_(*filters))
    
    total_res = await db.execute(count_query)
    total_count = total_res.scalar()
    
    # Execute query
    res = await db.execute(query.offset(offset).limit(limit))
    rows = res.all()
    
    jobs = []
    for row in rows:
        job, name, email = row
        job_dict = {c.name: getattr(job, c.name) for c in job.__table__.columns}
        
        # Safe ISO Formatting for UTC
        for key in ["started_at", "completed_at"]:
            ts = job_dict.get(key)
            if ts:
                job_dict[key] = ts.isoformat() + ("Z" if ts.tzinfo is None else "")
            
        job_dict["user_name"] = name
        job_dict["user_email"] = email
        jobs.append(job_dict)
    
    # Summary Stats
    stats_query = select(
        func.count(ScrapeJob.id).label("total_jobs"),
        func.sum(ScrapeJob.total_scraped).label("total_articles"),
        func.count(func.distinct(ScrapeJob.user_id)).label("active_users")
    )
    stats_res = await db.execute(stats_query)
    stats = stats_res.mappings().one()
    
    return {
        "jobs": jobs,
        "total": total_count,
        "page": page,
        "limit": limit,
        "summary": {
            "total_jobs": stats["total_jobs"] or 0,
            "total_articles": stats["total_articles"] or 0,
            "active_users": stats["active_users"] or 0
        }
    }

@router.get("/jobs/{job_id}")
async def get_job_detail(
    job_id: str,
    db: AsyncSession = Depends(get_db_yield),
    _admin: TokenData = Depends(get_admin_user)
):
    query = select(ScrapeJob, User.name, User.email).join(User, ScrapeJob.user_id == User.id, isouter=True).where(ScrapeJob.id == job_id)
    res = await db.execute(query)
    row = res.all() # Use all() and check length to avoid one_or_none issues with joins
    
    if not row:
        raise HTTPException(404, "Job not found")
        
    job, name, email = row[0]
    job_dict = {c.name: getattr(job, c.name) for c in job.__table__.columns}
    
    # Safe ISO Formatting for UTC
    for key in ["started_at", "completed_at"]:
        ts = job_dict.get(key)
        if ts:
            job_dict[key] = ts.isoformat() + ("Z" if ts.tzinfo is None else "")
        
    job_dict["user_name"] = name
    job_dict["user_email"] = email
    
    return job_dict

@router.get("/users")
async def list_admin_users(
    db: AsyncSession = Depends(get_db_yield),
    _admin: TokenData = Depends(get_admin_user)
):
    # List all users with job counts
    query = select(
        User.id,
        User.name,
        User.email,
        User.created_at,
        func.count(ScrapeJob.id).label("job_count"),
        func.sum(ScrapeJob.total_scraped).label("total_articles")
    ).outerjoin(ScrapeJob, User.id == ScrapeJob.user_id).group_by(User.id)
    
    res = await db.execute(query)
    rows = res.all()
    
    return [{
        "id": r.id,
        "name": r.name,
        "email": r.email,
        "created_at": r.created_at,
        "job_count": r.job_count,
        "total_articles": r.total_articles or 0
    } for r in rows]

@router.get("/users/{email}/jobs")
async def get_user_jobs(
    email: str,
    db: AsyncSession = Depends(get_db_yield),
    _admin: TokenData = Depends(get_admin_user)
):
    # Find user by email
    user_query = select(User).where(User.email == email)
    user_res = await db.execute(user_query)
    user = user_res.scalar_one_or_none()
    
    if not user:
        raise HTTPException(404, "User not found")
        
    # Get user jobs
    jobs_query = select(ScrapeJob).where(ScrapeJob.user_id == user.id).order_by(desc(ScrapeJob.started_at))
    jobs_res = await db.execute(jobs_query)
    jobs = jobs_res.scalars().all()
    
    # Per-user stats
    stats_query = select(
        func.count(ScrapeJob.id).label("total_jobs"),
        func.sum(ScrapeJob.total_scraped).label("total_articles"),
        func.mode().within_group(ScrapeJob.sector).label("most_searched_brand")
    ).where(ScrapeJob.user_id == user.id)
    
    # Note: postgres supports mode(), sqlite might not. Fallback for brand search:
    brand_query = select(ScrapeJob.sector, func.count(ScrapeJob.sector).label("count"))\
        .where(ScrapeJob.user_id == user.id)\
        .group_by(ScrapeJob.sector)\
        .order_by(desc("count"))\
        .limit(1)
    
    brand_res = await db.execute(brand_query)
    brand_row = brand_res.one_or_none()
    most_searched_brand = brand_row[0] if brand_row else None
    
    stats_res = await db.execute(select(func.count(ScrapeJob.id), func.sum(ScrapeJob.total_scraped)).where(ScrapeJob.user_id == user.id))
    job_count, article_sum = stats_res.one()
    
    # Brands/Keywords Watchlist
    brands_query = select(WatchedBrand).where(WatchedBrand.user_id == user.id)
    brands_res = await db.execute(brands_query)
    brands_orm = brands_res.scalars().all()
    
    # Explicit Dict Conversion (ORM objects aren't JSON serializable by default)
    # Also standardize ISO format with 'Z' for UTC if naive
    brands = []
    for b in brands_orm:
        brands.append({
            "id": b.id,
            "name": b.name,
            "region": b.region,
            "keywords": b.keywords,
            "last_scraped": b.last_scraped.isoformat() + ("Z" if b.last_scraped.tzinfo is None else "") if b.last_scraped else None
        })
    
    # Standardize Job timestamps
    formatted_jobs = []
    for j in jobs:
        # Note: 'j' is already an ORM object here, so we convert to dict
        j_dict = {c.name: getattr(j, c.name) for c in j.__table__.columns}
        for key in ["started_at", "completed_at"]:
            ts = j_dict.get(key)
            if ts:
                j_dict[key] = ts.isoformat() + ("Z" if ts.tzinfo is None else "")
        formatted_jobs.append(j_dict)
    
    return {
        "user": {"name": user.name, "email": user.email},
        "jobs": formatted_jobs,
        "brands": brands,
        "stats": {
            "total_jobs": job_count or 0,
            "total_articles": article_sum or 0,
            "most_searched_brand": most_searched_brand
        }
    }
