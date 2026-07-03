"""
NEXUS Feed API - Service API Key Integration
Provides machine-to-machine access to article data for analysis engines.
Authentication: Static service API key in environment variable.
"""
import os
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from sqlalchemy import select, func, and_
from db.database import get_db_yield, Article

router = APIRouter()

@router.get("/feed")
async def service_feed(
    api_key: str = Query(..., description="NEXUS_SERVICE_KEY"),
    sector: Optional[str] = None,
    date_filter: Optional[date] = Query(None, alias="date"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    has_body: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db=Query(None)  # Will be replaced with actual dependency
):
    """
    Machine-to-machine feed endpoint for external analysis engines.

    Filters articles by sector, date range, and content availability.
    Paginates results (max 500 per page).

    Auth: Static API key comparison against NEXUS_SERVICE_KEY env var.
    """
    # Get async db from dependency
    async for session in get_db_yield():
        db = session
        break

    # Auth: compare against env var — no DB lookup needed
    expected = os.getenv("NEXUS_SERVICE_KEY")
    if not expected or api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")

    page_size = min(page_size, 500)  # Hard cap at 500
    offset = (page - 1) * page_size

    # Build query
    stmt = select(Article)

    # Filters
    filters = []

    if sector:
        filters.append(Article.sector.ilike(f"%{sector}%"))

    if date_filter:
        filters.append(and_(
            Article.published_at >= date_filter,
            Article.published_at < date_filter + timedelta(days=1)
        ))

    if date_from:
        filters.append(Article.published_at >= date_from)

    if date_to:
        filters.append(Article.published_at <= date_to)

    if has_body is True:
        filters.append(and_(
            Article.full_body != None,
            func.length(Article.full_body) > 100
        ))

    if filters:
        stmt = stmt.where(and_(*filters))

    # Count total
    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar() or 0

    # Paginate and fetch
    stmt = stmt.order_by(Article.published_at.desc()).offset(offset).limit(page_size)
    articles = (await db.execute(stmt)).scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": -(-total // page_size) if total else 0,
        "articles": [
            {
                "id": a.id,
                "title": a.title,
                "url": a.url,
                "resolved_url": a.resolved_url,
                "full_body": a.full_body,
                "summary": a.summary,
                "author": a.author,
                "agency": a.agency,
                "published_at": a.published_at.isoformat() if a.published_at else None,
                "sector": a.sector,
                "region": a.region,
                "sentiment": a.sentiment,
                "tags": a.tags,
                "word_count": a.word_count,
                "scraped_at": a.scraped_at.isoformat() if a.scraped_at else None,
            }
            for a in articles
        ]
    }
