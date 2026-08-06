import json
import os
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import (
    get_db_yield,
    HeavyCompany, HeavyRecipient, HeavyRun, HeavyRunArticle,
)
from .auth_utils import get_auth_user, TokenData
from celery_app import app as celery_app

router = APIRouter(prefix="/heavy-automation", tags=["heavy-automation"])


async def get_admin_user(current_user: TokenData = Depends(get_auth_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class RecipientIn(BaseModel):
    email: EmailStr
    role: str = "brief"  # brief | master_doc

class CompanyCreate(BaseModel):
    name: str
    sector_match: str
    enabled: bool = True
    timezone: str = "Asia/Kolkata"
    fetch_time: str = "07:00"
    window_hours: int = 24
    relevancy_method: str = "Hybrid"
    relevance_context: Optional[str] = None
    relevance_threshold: float = 0.5
    llm_judge_enabled: bool = False
    pooja_algo_enabled: bool = False
    pooja_folder_filtering_enabled: bool = False
    pooja_priority_conf: int = 5
    pooja_non_priority_conf: int = 7
    email_send_reports: bool = True
    email_send_html: bool = False
    search_mode: str = "title"
    mail_send_mode: str = "Immediate"
    mail_send_time: Optional[str] = None
    frequency: str = "Daily"
    days: Optional[List[str]] = None
    takeaways_sheet_url: Optional[str] = None
    send_monthly_takeaways_enabled: bool = False
    monthly_takeaways_day: int = 1
    monthly_takeaways_time: str = "09:00"
    recipients: List[RecipientIn] = []

class RecipientOut(BaseModel):
    id: int
    email: str
    role: str

class CompanyOut(BaseModel):
    id: int
    name: str
    sector_match: str
    enabled: bool
    timezone: str
    fetch_time: str
    window_hours: int
    relevancy_method: str
    relevance_context: Optional[str]
    relevance_threshold: float
    llm_judge_enabled: bool
    pooja_algo_enabled: bool
    pooja_folder_filtering_enabled: bool
    pooja_priority_conf: int
    pooja_non_priority_conf: int
    email_send_reports: bool
    email_send_html: bool
    search_mode: str
    mail_send_mode: str
    mail_send_time: Optional[str]
    frequency: str
    days: Optional[List[str]]
    last_run_at: Optional[str]
    takeaways_sheet_url: Optional[str] = None
    send_monthly_takeaways_enabled: Optional[bool] = False
    monthly_takeaways_day: Optional[int] = 1
    monthly_takeaways_time: Optional[str] = "09:00"
    created_at: str
    recipients: List[RecipientOut]

class RunOut(BaseModel):
    id: int
    company_id: int
    status: str
    fetched_count: int
    deduped_count: int
    relevant_count: int
    master_doc_path: Optional[str]
    filtered_doc_path: Optional[str]
    master_excel_path: Optional[str]
    filtered_excel_path: Optional[str]
    google_doc_url: Optional[str] = None
    mailer_doc_path: Optional[str] = None
    email_status: Optional[str]
    progress_message: Optional[str]
    error: Optional[str]
    started_at: str
    finished_at: Optional[str]

class RunArticleOut(BaseModel):
    id: int
    title: Optional[str]
    url: Optional[str]
    published_at: Optional[str]
    relevance_score: Optional[float]
    included_in_brief: bool
    pillar: Optional[str]
    sub_category: Optional[str]
    matched_keywords: Optional[List[str]]
    llm_summary: Optional[str]
    bucket: Optional[str]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_dt(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.isoformat() + ("Z" if dt.tzinfo is None else "")

async def _build_company_out(company: HeavyCompany, db: AsyncSession) -> CompanyOut:
    rec_res = await db.execute(
        select(HeavyRecipient).where(HeavyRecipient.company_id == company.id)
    )
    recipients = [
        RecipientOut(id=r.id, email=r.email, role=r.role)
        for r in rec_res.scalars().all()
    ]
    days_val = json.loads(company.days) if company.days else None
    return CompanyOut(
        id=company.id,
        name=company.name,
        sector_match=company.sector_match,
        enabled=company.enabled,
        timezone=company.timezone,
        fetch_time=company.fetch_time,
        window_hours=company.window_hours,
        relevancy_method=company.relevancy_method,
        relevance_context=company.relevance_context,
        relevance_threshold=company.relevance_threshold,
        llm_judge_enabled=company.llm_judge_enabled,
        pooja_algo_enabled=getattr(company, 'pooja_algo_enabled', False),
        pooja_folder_filtering_enabled=getattr(company, 'pooja_folder_filtering_enabled', False),
        pooja_priority_conf=getattr(company, 'pooja_priority_conf', 5),
        pooja_non_priority_conf=getattr(company, 'pooja_non_priority_conf', 7),
        email_send_reports=getattr(company, 'email_send_reports', True),
        email_send_html=getattr(company, 'email_send_html', False),
        search_mode=company.search_mode if company.search_mode else "title",
        mail_send_mode=company.mail_send_mode,
        mail_send_time=company.mail_send_time,
        frequency=company.frequency,
        days=days_val,
        last_run_at=_fmt_dt(company.last_run_at),
        takeaways_sheet_url=company.takeaways_sheet_url,
        send_monthly_takeaways_enabled=bool(company.send_monthly_takeaways_enabled) if company.send_monthly_takeaways_enabled is not None else False,
        monthly_takeaways_day=int(company.monthly_takeaways_day) if company.monthly_takeaways_day is not None else 1,
        monthly_takeaways_time=str(company.monthly_takeaways_time) if company.monthly_takeaways_time else "09:00",
        created_at=_fmt_dt(company.created_at),
        recipients=recipients,
    )


# ── Company CRUD ──────────────────────────────────────────────────────────────

@router.get("/companies", response_model=List[CompanyOut])
async def list_companies(
    db: AsyncSession = Depends(get_db_yield),
    _: TokenData = Depends(get_admin_user),
):
    res = await db.execute(select(HeavyCompany).order_by(HeavyCompany.name))
    companies = res.scalars().all()
    return [await _build_company_out(c, db) for c in companies]


@router.post("/companies", response_model=CompanyOut)
async def create_company(
    payload: CompanyCreate,
    db: AsyncSession = Depends(get_db_yield),
    _: TokenData = Depends(get_admin_user),
):
    existing = await db.execute(select(HeavyCompany).where(HeavyCompany.name == payload.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Company with this name already exists")

    company = HeavyCompany(
        name=payload.name,
        sector_match=payload.sector_match,
        enabled=payload.enabled,
        timezone=payload.timezone,
        fetch_time=payload.fetch_time,
        window_hours=payload.window_hours,
        relevancy_method=payload.relevancy_method,
        relevance_context=payload.relevance_context,
        relevance_threshold=payload.relevance_threshold,
        llm_judge_enabled=payload.llm_judge_enabled,
        pooja_algo_enabled=payload.pooja_algo_enabled,
        pooja_folder_filtering_enabled=payload.pooja_folder_filtering_enabled,
        pooja_priority_conf=payload.pooja_priority_conf,
        pooja_non_priority_conf=payload.pooja_non_priority_conf,
        email_send_reports=payload.email_send_reports,
        email_send_html=payload.email_send_html,
        search_mode=payload.search_mode,
        mail_send_mode=payload.mail_send_mode,
        mail_send_time=payload.mail_send_time,
        frequency=payload.frequency,
        days=json.dumps(payload.days) if payload.days else None,
        takeaways_sheet_url=payload.takeaways_sheet_url,
        send_monthly_takeaways_enabled=payload.send_monthly_takeaways_enabled,
        monthly_takeaways_day=payload.monthly_takeaways_day,
        monthly_takeaways_time=payload.monthly_takeaways_time,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)

    for r in payload.recipients:
        db.add(HeavyRecipient(company_id=company.id, email=r.email, role=r.role))
    await db.commit()

    return await _build_company_out(company, db)


@router.put("/companies/{company_id}", response_model=CompanyOut)
async def update_company(
    company_id: int,
    payload: CompanyCreate,
    db: AsyncSession = Depends(get_db_yield),
    _: TokenData = Depends(get_admin_user),
):
    res = await db.execute(select(HeavyCompany).where(HeavyCompany.id == company_id))
    company = res.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    company.name = payload.name
    company.sector_match = payload.sector_match
    company.enabled = payload.enabled
    company.timezone = payload.timezone
    company.fetch_time = payload.fetch_time
    company.window_hours = payload.window_hours
    company.relevancy_method = payload.relevancy_method
    company.relevance_context = payload.relevance_context
    company.relevance_threshold = payload.relevance_threshold
    company.llm_judge_enabled = payload.llm_judge_enabled
    company.pooja_algo_enabled = payload.pooja_algo_enabled
    company.pooja_folder_filtering_enabled = payload.pooja_folder_filtering_enabled
    company.pooja_priority_conf = payload.pooja_priority_conf
    company.pooja_non_priority_conf = payload.pooja_non_priority_conf
    company.email_send_reports = payload.email_send_reports
    company.email_send_html = payload.email_send_html
    company.search_mode = payload.search_mode
    company.mail_send_mode = payload.mail_send_mode
    company.mail_send_time = payload.mail_send_time
    company.frequency = payload.frequency
    company.days = json.dumps(payload.days) if payload.days else None
    company.takeaways_sheet_url = payload.takeaways_sheet_url
    company.send_monthly_takeaways_enabled = payload.send_monthly_takeaways_enabled
    company.monthly_takeaways_day = payload.monthly_takeaways_day
    company.monthly_takeaways_time = payload.monthly_takeaways_time
    company.updated_at = datetime.now()

    await db.execute(delete(HeavyRecipient).where(HeavyRecipient.company_id == company_id))
    for r in payload.recipients:
        db.add(HeavyRecipient(company_id=company_id, email=r.email, role=r.role))

    await db.commit()
    await db.refresh(company)
    return await _build_company_out(company, db)


@router.delete("/companies/{company_id}")
async def delete_company(
    company_id: int,
    db: AsyncSession = Depends(get_db_yield),
    _: TokenData = Depends(get_admin_user),
):
    res = await db.execute(select(HeavyCompany).where(HeavyCompany.id == company_id))
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Company not found")
    await db.execute(delete(HeavyCompany).where(HeavyCompany.id == company_id))
    await db.commit()
    return {"detail": "Company deleted"}


# ── Run trigger & history ─────────────────────────────────────────────────────

@router.post("/companies/{company_id}/run")
async def trigger_run(
    company_id: int,
    db: AsyncSession = Depends(get_db_yield),
    _: TokenData = Depends(get_admin_user),
):
    res = await db.execute(select(HeavyCompany).where(HeavyCompany.id == company_id))
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Company not found")

    task = celery_app.send_task(
        "scraper.tasks.run_heavy_automation_task",
        args=[company_id],
    )
    return {"detail": "Heavy automation task triggered", "task_id": task.id}


@router.get("/companies/{company_id}/takeaways-link")
async def get_takeaways_link(
    company_id: int,
    db: AsyncSession = Depends(get_db_yield),
    _: TokenData = Depends(get_admin_user),
):
    res = await db.execute(select(HeavyCompany).where(HeavyCompany.id == company_id))
    company = res.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return {"takeaways_sheet_url": company.takeaways_sheet_url}


@router.get("/companies/{company_id}/runs", response_model=List[RunOut])
async def get_runs(
    company_id: int,
    db: AsyncSession = Depends(get_db_yield),
    _: TokenData = Depends(get_admin_user),
):
    res = await db.execute(
        select(HeavyRun)
        .where(HeavyRun.company_id == company_id)
        .order_by(desc(HeavyRun.started_at))
        .limit(50)
    )
    runs = res.scalars().all()
    return [
        RunOut(
            id=r.id,
            company_id=r.company_id,
            status=r.status,
            fetched_count=r.fetched_count,
            deduped_count=r.deduped_count,
            relevant_count=r.relevant_count,
            master_doc_path=os.path.basename(r.master_doc_path) if r.master_doc_path else None,
            filtered_doc_path=os.path.basename(r.filtered_doc_path) if r.filtered_doc_path else None,
            master_excel_path=os.path.basename(r.master_excel_path) if r.master_excel_path else None,
            filtered_excel_path=os.path.basename(r.filtered_excel_path) if r.filtered_excel_path else None,
            google_doc_url=getattr(r, 'google_doc_url', None),
            mailer_doc_path=os.path.basename(r.mailer_doc_path) if getattr(r, 'mailer_doc_path', None) else None,
            email_status=r.email_status,
            progress_message=r.progress_message,
            error=r.error,
            started_at=_fmt_dt(r.started_at),
            finished_at=_fmt_dt(r.finished_at),
        )
        for r in runs
    ]


@router.get("/runs/{run_id}/articles", response_model=List[RunArticleOut])
async def get_run_articles(
    run_id: int,
    db: AsyncSession = Depends(get_db_yield),
    _: TokenData = Depends(get_admin_user),
):
    res = await db.execute(
        select(HeavyRunArticle)
        .where(HeavyRunArticle.run_id == run_id)
        .order_by(desc(HeavyRunArticle.relevance_score))
        .limit(500)
    )
    articles = res.scalars().all()
    return [
        RunArticleOut(
            id=a.id,
            title=a.title,
            url=a.url,
            published_at=_fmt_dt(a.published_at),
            relevance_score=a.relevance_score,
            included_in_brief=a.included_in_brief,
            pillar=a.pillar,
            sub_category=a.sub_category,
            matched_keywords=json.loads(a.matched_keywords) if a.matched_keywords else None,
            llm_summary=a.llm_summary,
            bucket=a.bucket,
        )
        for a in articles
    ]


# ── Report download ───────────────────────────────────────────────────────────

# ── Threshold preview (Phase 5) ───────────────────────────────────────────

@router.post("/companies/{company_id}/preview")
async def preview_threshold(
    company_id: int,
    db: AsyncSession = Depends(get_db_yield),
    _: TokenData = Depends(get_admin_user),
):
    """
    Preview how many articles remain at different threshold values.
    Runs the full filter pipeline without generating reports.
    """
    res = await db.execute(select(HeavyCompany).where(HeavyCompany.id == company_id))
    company = res.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    try:
        from datetime import datetime, timedelta
        from db.database import Article
        from scraper.heavy_filter import exact_dedup, near_dedup, bucket_articles

        # Fetch articles (same logic as task)
        cutoff = datetime.utcnow() - timedelta(hours=company.window_hours)
        from sqlalchemy import or_
        sectors = [s.strip() for s in company.sector_match.split(",") if s.strip()]
        sector_filters = [Article.sector.ilike(f"%{s}%") for s in sectors]

        articles = await db.execute(
            select(Article).where(
                or_(*sector_filters),
                Article.published_at >= cutoff,
            ).limit(5000)
        )
        fetched = [
            {
                "id": a.id,
                "title": a.title,
                "url": a.resolved_url or a.url,
                "full_body": a.full_body,
                "summary": a.summary,
                "published_at": a.published_at,
            }
            for a in articles.scalars().all()
        ]

        if not fetched:
            return {
                "fetched": 0,
                "deduped": 0,
                "preview": [
                    {"threshold": 0.2, "keep": 0, "ambiguous": 0, "discard": 0},
                    {"threshold": 0.5, "keep": 0, "ambiguous": 0, "discard": 0},
                    {"threshold": 0.8, "keep": 0, "ambiguous": 0, "discard": 0},
                ],
            }

        # Dedup
        deduped_exact = exact_dedup(fetched)
        deduped = near_dedup(deduped_exact, threshold=0.80)

        # Preview at different thresholds
        preview = []
        for threshold in [0.2, 0.35, 0.5, 0.65, 0.8]:
            clear_keep, ambiguous_middle, clear_discard = bucket_articles(deduped, threshold=threshold)
            preview.append({
                "threshold": threshold,
                "keep": len(clear_keep),
                "ambiguous": len(ambiguous_middle),
                "discard": len(clear_discard),
            })

        return {
            "fetched": len(fetched),
            "deduped": len(deduped),
            "preview": preview,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")


# ── Report download ───────────────────────────────────────────────────────────

@router.get("/reports/{filename}")
async def download_report(
    filename: str,
    db: AsyncSession = Depends(get_db_yield),
    _: TokenData = Depends(get_admin_user),
):
    reports_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports"
    )
    file_path = os.path.join(reports_dir, filename)

    # Path traversal guard
    if not os.path.realpath(file_path).startswith(os.path.realpath(reports_dir)):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(file_path):
        # Dynamically restore from DB
        stmt = select(HeavyRun).where(
            (HeavyRun.master_doc_path.like(f"%{filename}%")) |
            (HeavyRun.filtered_doc_path.like(f"%{filename}%")) |
            (HeavyRun.master_excel_path.like(f"%{filename}%")) |
            (HeavyRun.filtered_excel_path.like(f"%{filename}%")) |
            (HeavyRun.mailer_doc_path.like(f"%{filename}%"))
        )
        res = await db.execute(stmt)
        run_rec = res.scalar_one_or_none()
        if run_rec:
            # Determine which column matches
            data_bytes = None
            if run_rec.master_doc_path and filename.lower() in run_rec.master_doc_path.lower():
                data_bytes = run_rec.master_doc_data
            elif run_rec.filtered_doc_path and filename.lower() in run_rec.filtered_doc_path.lower():
                data_bytes = run_rec.filtered_doc_data
            elif run_rec.master_excel_path and filename.lower() in run_rec.master_excel_path.lower():
                data_bytes = run_rec.master_excel_data
            elif run_rec.filtered_excel_path and filename.lower() in run_rec.filtered_excel_path.lower():
                data_bytes = run_rec.filtered_excel_data
            elif run_rec.mailer_doc_path and filename.lower() in run_rec.mailer_doc_path.lower():
                data_bytes = run_rec.mailer_doc_data

            if data_bytes:
                try:
                    os.makedirs(reports_dir, exist_ok=True)
                    with open(file_path, "wb") as buffer:
                        buffer.write(data_bytes)
                except Exception:
                    pass

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    media_type = "application/octet-stream"
    if filename.endswith(".docx"):
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif filename.endswith(".xlsx"):
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    return FileResponse(
        file_path,
        media_type=media_type,
        filename=filename,
    )


SECTOR_VARIANTS = {
    'tech': ['tech', 'Tech', 'TECH', 'Techhh', 'tech1', 'teccH', 'Tech1', 'TeccH'],
    'stock market': ['stock market', 'Stock Market'],
    'policies': ['policies', 'Policies'],
    'real estate': ['real estate', 'Real Estate'],
    'healthcare': ['healthcare', 'HEALTHCARE', 'HealthCare', 'Health'],
    'startups': ['startups', 'StartUp'],
    'foods and drinks': ['foods and drinks', 'FOODS AND DRINKS', 'Foods'],
    'ai': ['ai', 'AI', 'Ai'],
    'google': ['google', 'google 2', 'google 3', 'Google3'],
    'travel': ['travel', 'Travell'],
    'lifestyle': ['lifestyle', 'LifeStyle'],
    'consultancies': ['consultancies', 'Consultancies'],
    'fintech': ['fintech', 'Fintech', 'FinTech', 'FINTECH'],
    'automobile': ['automobile', 'Automobile', 'auto', 'Auto', 'AUTOMOBILE'],
    'media and entertainment': ['media and entertainment', 'Media and Entertainment', 'media', 'Media', 'entertainment', 'Entertainment'],
    'education': ['education', 'Education', 'EDUCATION']
}

NEXUS_SECTORS = [
    'ai', 'automobile', 'consultancies', 'education', 'fintech', 'foods and drinks', 'google', 'healthcare',
    'lifestyle', 'media and entertainment', 'policies', 'real estate', 'startups', 'stock market', 'tech', 'travel'
]

@router.get("/nexus-sectors")
async def get_nexus_sectors(_: TokenData = Depends(get_admin_user)):
    """Return the list of available sectors from the Nexus production feed."""
    return {"sectors": NEXUS_SECTORS}



@router.get("/nexus-stats")
async def get_nexus_stats(_: TokenData = Depends(get_admin_user)):
    """
    Fetch all-time and last 24h sector/article counts from Nexus production server.
    All requests fired in parallel with asyncio.gather for speed.
    """
    import httpx
    import asyncio
    base_url = "http://34.142.240.96"
    api_key = os.getenv("NEXUS_SERVICE_KEY", "nexus_sk_fb74eaae34cd3e53f6ac2031479337cb")

    from datetime import datetime, timedelta
    past_24h_date = (datetime.utcnow() - timedelta(hours=24)).date().isoformat()

    async with httpx.AsyncClient(timeout=10.0) as client:
        async def fetch_total():
            try:
                r = await client.get(f"{base_url}/api/feed?api_key={api_key}&page_size=1")
                return r.json().get("total", 0) if r.status_code == 200 else 0
            except Exception:
                return 0

        async def fetch_sector(sec):
            variants = SECTOR_VARIANTS.get(sec, [sec])
            
            async def fetch_variant(v):
                try:
                    r_all, r_24h = await asyncio.gather(
                        client.get(f"{base_url}/api/feed?api_key={api_key}&sector={v}&page_size=1"),
                        client.get(f"{base_url}/api/feed?api_key={api_key}&sector={v}&date_from={past_24h_date}&page_size=1"),
                    )
                    count_all = r_all.json().get("total", 0) if r_all.status_code == 200 else 0
                    count_24h = r_24h.json().get("total", 0) if r_24h.status_code == 200 else 0
                except Exception:
                    count_all, count_24h = 0, 0
                return count_all, count_24h

            # Query all variations of the sector concurrently
            results = await asyncio.gather(*[fetch_variant(v) for v in variants])
            total_all = sum(res[0] for res in results)
            total_24h = sum(res[1] for res in results)
            return {"sector": sec, "count_24h": total_24h, "count_all": total_all}

        results = await asyncio.gather(
            fetch_total(),
            *[fetch_sector(sec) for sec in NEXUS_SECTORS]
        )

    return {
        "total_articles": results[0],
        "sector_stats": list(results[1:]),
    }

