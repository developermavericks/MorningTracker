import json
import os
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import (
    get_db_yield,
    RobustCompany, RobustRecipient, RobustRun, RobustRunArticle,
)
from .auth_utils import get_auth_user, TokenData
from celery_app import app as celery_app

router = APIRouter(prefix="/robust-automation", tags=["robust-automation"])


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
    
    # Output delivery toggles
    send_email: bool = True
    send_html_mailer: bool = True
    send_mailer_doc: bool = True
    send_report_doc: bool = True
    send_report_excel: bool = True
    upload_to_google_drive: bool = False
    update_takeaways_sheet: bool = False
    
    # LLM Settings
    llm_verification_provider: str = "none"
    llm_summary_provider: str = "none"
    llm_executive_provider: str = "none"
    
    # Schedulers
    mail_send_mode: str = "Immediate"
    mail_send_time: Optional[str] = "08:00"
    frequency: str = "Daily"
    days: Optional[List[str]] = None
    
    # Takeaways Google Sheet
    takeaways_sheet_url: Optional[str] = None
    send_monthly_takeaways_enabled: bool = False
    monthly_takeaways_day: int = 1
    monthly_takeaways_time: str = "09:00"
    
    manual_keywords: Optional[str] = None
    search_mode: str = "title"
    pooja_algo_enabled: bool = True
    group_by_source_sector: bool = False
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
    
    # Files metadata
    keywords_file_name: Optional[str]
    priority_media_file_name: Optional[str]
    
    # Output delivery toggles
    send_email: bool
    send_html_mailer: bool
    send_mailer_doc: bool
    send_report_doc: bool
    send_report_excel: bool
    upload_to_google_drive: bool
    update_takeaways_sheet: bool
    
    # LLM Settings
    llm_verification_provider: str
    llm_summary_provider: str
    llm_executive_provider: str
    
    # Schedulers
    mail_send_mode: str
    mail_send_time: Optional[str]
    frequency: str
    days: Optional[List[str]]
    last_run_at: Optional[str]
    
    # Takeaways Google Sheet
    takeaways_sheet_url: Optional[str]
    send_monthly_takeaways_enabled: bool
    monthly_takeaways_day: int
    monthly_takeaways_time: str
    manual_keywords: Optional[str]
    search_mode: str
    pooja_algo_enabled: bool
    group_by_source_sector: bool
    
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
    google_doc_url: Optional[str]
    mailer_doc_path: Optional[str]
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

async def _build_company_out(company: RobustCompany, db: AsyncSession) -> CompanyOut:
    rec_res = await db.execute(
        select(RobustRecipient).where(RobustRecipient.company_id == company.id)
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
        keywords_file_name=company.keywords_file_name,
        priority_media_file_name=company.priority_media_file_name,
        send_email=company.send_email,
        send_html_mailer=company.send_html_mailer,
        send_mailer_doc=company.send_mailer_doc,
        send_report_doc=company.send_report_doc,
        send_report_excel=company.send_report_excel,
        upload_to_google_drive=company.upload_to_google_drive,
        update_takeaways_sheet=company.update_takeaways_sheet,
        llm_verification_provider=company.llm_verification_provider,
        llm_summary_provider=company.llm_summary_provider,
        llm_executive_provider=company.llm_executive_provider,
        mail_send_mode=company.mail_send_mode,
        mail_send_time=company.mail_send_time,
        frequency=company.frequency,
        days=days_val,
        last_run_at=_fmt_dt(company.last_run_at),
        takeaways_sheet_url=company.takeaways_sheet_url,
        send_monthly_takeaways_enabled=company.send_monthly_takeaways_enabled,
        monthly_takeaways_day=company.monthly_takeaways_day,
        monthly_takeaways_time=company.monthly_takeaways_time,
        manual_keywords=company.manual_keywords,
        search_mode=company.search_mode,
        pooja_algo_enabled=company.pooja_algo_enabled,
        group_by_source_sector=company.group_by_source_sector,
        created_at=_fmt_dt(company.created_at),
        recipients=recipients,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/companies", response_model=List[CompanyOut], dependencies=[Depends(get_admin_user)])
async def get_companies(db: AsyncSession = Depends(get_db_yield)):
    res = await db.execute(select(RobustCompany).order_by(RobustCompany.name))
    companies = res.scalars().all()
    out = []
    for c in companies:
        out.append(await _build_company_out(c, db))
    return out


@router.post("/companies", response_model=CompanyOut, dependencies=[Depends(get_admin_user)])
async def create_company(body: CompanyCreate, db: AsyncSession = Depends(get_db_yield)):
    # Check duplicate name
    dup_res = await db.execute(select(RobustCompany).where(RobustCompany.name == body.name))
    if dup_res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Company name already exists")

    days_str = json.dumps(body.days) if body.days is not None else None

    company = RobustCompany(
        name=body.name,
        sector_match=body.sector_match,
        enabled=body.enabled,
        timezone=body.timezone,
        fetch_time=body.fetch_time,
        window_hours=body.window_hours,
        send_email=body.send_email,
        send_html_mailer=body.send_html_mailer,
        send_mailer_doc=body.send_mailer_doc,
        send_report_doc=body.send_report_doc,
        send_report_excel=body.send_report_excel,
        upload_to_google_drive=body.upload_to_google_drive,
        update_takeaways_sheet=body.update_takeaways_sheet,
        llm_verification_provider=body.llm_verification_provider,
        llm_summary_provider=body.llm_summary_provider,
        llm_executive_provider=body.llm_executive_provider,
        mail_send_mode=body.mail_send_mode,
        mail_send_time=body.mail_send_time,
        frequency=body.frequency,
        days=days_str,
        takeaways_sheet_url=body.takeaways_sheet_url,
        send_monthly_takeaways_enabled=body.send_monthly_takeaways_enabled,
        monthly_takeaways_day=body.monthly_takeaways_day,
        monthly_takeaways_time=body.monthly_takeaways_time,
        manual_keywords=body.manual_keywords,
        search_mode=body.search_mode,
        pooja_algo_enabled=body.pooja_algo_enabled,
        group_by_source_sector=body.group_by_source_sector,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)

    # Add recipients
    for r in body.recipients:
        rec = RobustRecipient(company_id=company.id, email=r.email, role=r.role)
        db.add(rec)
    await db.commit()

    return await _build_company_out(company, db)


@router.put("/companies/{id}", response_model=CompanyOut, dependencies=[Depends(get_admin_user)])
async def update_company_endpoint(id: int, body: CompanyCreate, db: AsyncSession = Depends(get_db_yield)):
    res = await db.execute(select(RobustCompany).where(RobustCompany.id == id))
    company = res.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Name duplicate check (if changed)
    if company.name != body.name:
        dup_res = await db.execute(select(RobustCompany).where(RobustCompany.name == body.name))
        if dup_res.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Company name already exists")

    days_str = json.dumps(body.days) if body.days is not None else None

    company.name = body.name
    company.sector_match = body.sector_match
    company.enabled = body.enabled
    company.timezone = body.timezone
    company.fetch_time = body.fetch_time
    company.window_hours = body.window_hours
    company.send_email = body.send_email
    company.send_html_mailer = body.send_html_mailer
    company.send_mailer_doc = body.send_mailer_doc
    company.send_report_doc = body.send_report_doc
    company.send_report_excel = body.send_report_excel
    company.upload_to_google_drive = body.upload_to_google_drive
    company.update_takeaways_sheet = body.update_takeaways_sheet
    company.llm_verification_provider = body.llm_verification_provider
    company.llm_summary_provider = body.llm_summary_provider
    company.llm_executive_provider = body.llm_executive_provider
    company.mail_send_mode = body.mail_send_mode
    company.mail_send_time = body.mail_send_time
    company.frequency = body.frequency
    company.days = days_str
    company.takeaways_sheet_url = body.takeaways_sheet_url
    company.send_monthly_takeaways_enabled = body.send_monthly_takeaways_enabled
    company.monthly_takeaways_day = body.monthly_takeaways_day
    company.monthly_takeaways_time = body.monthly_takeaways_time
    company.manual_keywords = body.manual_keywords
    company.search_mode = body.search_mode
    company.pooja_algo_enabled = body.pooja_algo_enabled
    company.group_by_source_sector = body.group_by_source_sector

    # Synchronize recipients
    await db.execute(delete(RobustRecipient).where(RobustRecipient.company_id == id))
    for r in body.recipients:
        rec = RobustRecipient(company_id=id, email=r.email, role=r.role)
        db.add(rec)

    await db.commit()
    await db.refresh(company)
    return await _build_company_out(company, db)


@router.delete("/companies/{id}", dependencies=[Depends(get_admin_user)])
async def delete_company_endpoint(id: int, db: AsyncSession = Depends(get_db_yield)):
    res = await db.execute(select(RobustCompany).where(RobustCompany.id == id))
    company = res.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    await db.delete(company)
    await db.commit()
    return {"status": "ok"}


@router.post("/companies/{id}/upload-keywords", dependencies=[Depends(get_admin_user)])
async def upload_keywords(id: int, file: UploadFile = File(...), db: AsyncSession = Depends(get_db_yield)):
    res = await db.execute(select(RobustCompany).where(RobustCompany.id == id))
    company = res.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    content = await file.read()
    company.keywords_file_name = file.filename
    company.keywords_file_data = content
    await db.commit()

    return {"status": "ok", "filename": file.filename}


@router.post("/companies/{id}/upload-priority-media", dependencies=[Depends(get_admin_user)])
async def upload_priority_media(id: int, file: UploadFile = File(...), db: AsyncSession = Depends(get_db_yield)):
    res = await db.execute(select(RobustCompany).where(RobustCompany.id == id))
    company = res.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    content = await file.read()
    company.priority_media_file_name = file.filename
    company.priority_media_file_data = content
    await db.commit()

    return {"status": "ok", "filename": file.filename}


@router.post("/companies/{id}/run", dependencies=[Depends(get_admin_user)])
async def trigger_company_run(id: int, db: AsyncSession = Depends(get_db_yield)):
    res = await db.execute(select(RobustCompany).where(RobustCompany.id == id))
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Company not found")

    # Launch Celery task
    celery_app.send_task("scraper.tasks.run_robust_automation_task", args=[id])
    return {"status": "ok"}


@router.get("/companies/{id}/runs", response_model=List[RunOut], dependencies=[Depends(get_admin_user)])
async def get_runs(id: int, db: AsyncSession = Depends(get_db_yield)):
    res = await db.execute(
        select(RobustRun)
        .where(RobustRun.company_id == id)
        .order_by(desc(RobustRun.started_at))
        .limit(30)
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
            master_doc_path=r.master_doc_path,
            filtered_doc_path=r.filtered_doc_path,
            master_excel_path=r.master_excel_path,
            filtered_excel_path=r.filtered_excel_path,
            google_doc_url=r.google_doc_url,
            mailer_doc_path=r.mailer_doc_path,
            email_status=r.email_status,
            progress_message=r.progress_message,
            error=r.error,
            started_at=_fmt_dt(r.started_at),
            finished_at=_fmt_dt(r.finished_at),
        )
        for r in runs
    ]


@router.get("/runs/{run_id}/articles", response_model=List[RunArticleOut], dependencies=[Depends(get_admin_user)])
async def get_run_articles(run_id: int, db: AsyncSession = Depends(get_db_yield)):
    res = await db.execute(
        select(RobustRunArticle)
        .where(RobustRunArticle.run_id == run_id)
        .order_by(desc(RobustRunArticle.relevance_score))
    )
    articles = res.scalars().all()
    out = []
    for a in articles:
        kws = json.loads(a.matched_keywords) if a.matched_keywords else []
        out.append(
            RunArticleOut(
                id=a.id,
                title=a.title,
                url=a.url,
                published_at=_fmt_dt(a.published_at),
                relevance_score=a.relevance_score,
                included_in_brief=a.included_in_brief,
                pillar=a.pillar,
                sub_category=a.sub_category,
                matched_keywords=kws,
                llm_summary=a.llm_summary,
                bucket=a.bucket,
            )
        )
    return out


# Download endpoint for report artifacts
@router.get("/reports/{filename}", dependencies=[Depends(get_admin_user)])
async def download_report_file(filename: str, db: AsyncSession = Depends(get_db_yield)):
    # Guard against directory traversal
    filename = os.path.basename(filename)
    reports_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
    file_path = os.path.join(reports_dir, filename)

    if not os.path.realpath(file_path).startswith(os.path.realpath(reports_dir)):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(file_path):
        # Dynamically restore from DB
        run_rec = None
        import re
        m = re.search(r"_Run_(\d+)\.csv", filename, re.IGNORECASE)
        if m:
            run_id = int(m.group(1))
            res = await db.execute(select(RobustRun).where(RobustRun.id == run_id))
            run_rec = res.scalar_one_or_none()
        else:
            stmt = select(RobustRun).where(
                (RobustRun.master_doc_path.like(f"%{filename}%")) |
                (RobustRun.filtered_doc_path.like(f"%{filename}%")) |
                (RobustRun.master_excel_path.like(f"%{filename}%")) |
                (RobustRun.filtered_excel_path.like(f"%{filename}%")) |
                (RobustRun.mailer_doc_path.like(f"%{filename}%"))
            )
            res = await db.execute(stmt)
            run_rec = res.scalar_one_or_none()

        if run_rec:
            data_bytes = None
            if "Robust_Fetched_Articles_Run_" in filename:
                data_bytes = run_rec.fetched_csv_data
            elif "Robust_Deduplicated_Articles_Run_" in filename:
                data_bytes = run_rec.deduped_csv_data
            elif "Robust_Pooja_Filtered_Articles_Run_" in filename:
                data_bytes = run_rec.pooja_csv_data
            elif "Robust_LLM_Verified_Articles_Run_" in filename:
                data_bytes = run_rec.verified_csv_data
            elif run_rec.master_doc_path and filename.lower() in run_rec.master_doc_path.lower():
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


# Sector choices mapping endpoint
@router.get("/nexus-sectors", dependencies=[Depends(get_admin_user)])
async def get_robust_nexus_sectors():
    """Return the normalized, merged list of all sectors for Robust Automation."""
    EXCLUDE_SECTORS = {"test545", "testing", "playwright test 2"}
    MERGE_MAPPING = {
        "travell": "travel",
        "techhh": "tech",
        "foods": "foods and drinks"
    }
    
    raw_sectors = [
        'ai', 'automobile', 'boston company', 'boston competition landscape', 'boston imp laws', 
        'boston industry', 'boston therapies / product', 'consultancies', 'education', 'fintech', 
        'foods', 'foods and drinks', 'google', 'healthcare', 'lifestyle', 'media and entertainment', 
        'playwright test 2', 'policies', 'real estate', 'startups', 'stock market', 'tech', 
        'techhh', 'test545', 'testing', 'travel', 'travell'
    ]
    
    norm_set = set()
    for s in raw_sectors:
        s_clean = s.strip().lower()
        if not s_clean or s_clean in EXCLUDE_SECTORS:
            continue
        normalized = MERGE_MAPPING.get(s_clean, s_clean)
        norm_set.add(normalized)
        
    sorted_sectors = sorted(list(norm_set))
    return {"sectors": sorted_sectors}


