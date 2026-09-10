import io
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
    RobustCompany, RobustRecipient, RobustRun, RobustRunArticle, RobustPromptHistory
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
    
    # Custom Prompts
    verification_system_prompt: Optional[str] = None
    verification_user_prompt: Optional[str] = None
    summary_user_prompt: Optional[str] = None
    executive_user_prompt: Optional[str] = None
    
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
    verification_doc_filename: Optional[str]
    verification_doc_text: Optional[str]
    
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
    
    # Custom Prompts
    verification_system_prompt: Optional[str]
    verification_user_prompt: Optional[str]
    summary_user_prompt: Optional[str]
    executive_user_prompt: Optional[str]
    
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

class PromptHistoryOut(BaseModel):
    id: int
    company_id: int
    stage: str
    system_prompt: Optional[str]
    user_prompt: str
    version_note: Optional[str]
    created_at: str
    created_by: str

class RestorePromptIn(BaseModel):
    history_id: int

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
        verification_doc_filename=company.verification_doc_filename,
        verification_doc_text=company.verification_doc_text,
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
        verification_system_prompt=company.verification_system_prompt,
        verification_user_prompt=company.verification_user_prompt,
        summary_user_prompt=company.summary_user_prompt,
        executive_user_prompt=company.executive_user_prompt,
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

    # Check prompt history tracking for changes
    if body.verification_user_prompt and body.verification_user_prompt != company.verification_user_prompt:
        hist_v = RobustPromptHistory(
            company_id=id,
            stage="verification",
            system_prompt=body.verification_system_prompt,
            user_prompt=body.verification_user_prompt,
            version_note="Prompt updated via Switchboard",
            created_by="Admin"
        )
        db.add(hist_v)
    if body.summary_user_prompt and body.summary_user_prompt != company.summary_user_prompt:
        hist_s = RobustPromptHistory(
            company_id=id,
            stage="summary",
            system_prompt=None,
            user_prompt=body.summary_user_prompt,
            version_note="Summary Prompt updated via Switchboard",
            created_by="Admin"
        )
        db.add(hist_s)
    if body.executive_user_prompt and body.executive_user_prompt != company.executive_user_prompt:
        hist_e = RobustPromptHistory(
            company_id=id,
            stage="executive",
            system_prompt=None,
            user_prompt=body.executive_user_prompt,
            version_note="Executive Synthesis Prompt updated via Switchboard",
            created_by="Admin"
        )
        db.add(hist_e)

    company.verification_system_prompt = body.verification_system_prompt
    company.verification_user_prompt = body.verification_user_prompt
    company.summary_user_prompt = body.summary_user_prompt
    company.executive_user_prompt = body.executive_user_prompt

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


def _smart_extract_pdf_content(content: bytes) -> str:
    try:
        import pdfplumber
        import re
        output_lines = []
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                table_objs = page.find_tables()
                tables_data = page.extract_tables()
                
                t_boxes = []
                for t_obj, t_data in zip(table_objs, tables_data):
                    if t_data:
                        t_boxes.append((t_obj.bbox[1], t_obj.bbox[3], t_data))
                
                words = page.extract_words()
                header_words = []
                for w in words:
                    inside_table = False
                    for top, bottom, _ in t_boxes:
                        if top - 2 <= w['top'] <= bottom + 2:
                            inside_table = True
                            break
                    if not inside_table:
                        header_words.append(w)
                
                header_lines = []
                if header_words:
                    header_words.sort(key=lambda item: (item['top'], item['x0']))
                    current_line = []
                    last_top = None
                    for w in header_words:
                        if last_top is None or abs(w['top'] - last_top) < 4:
                            current_line.append(w['text'])
                            last_top = w['top']
                        else:
                            header_lines.append((last_top, ' '.join(current_line)))
                            current_line = [w['text']]
                            last_top = w['top']
                    if current_line:
                        header_lines.append((last_top, ' '.join(current_line)))
                
                page_elements = []
                for top_pos, line_text in header_lines:
                    clean_text = line_text.strip()
                    if clean_text:
                        page_elements.append((top_pos, 'header', clean_text))
                
                for top_pos, bottom_pos, t_data in t_boxes:
                    page_elements.append((top_pos, 'table', t_data))
                
                page_elements.sort(key=lambda item: item[0])
                
                for elem in page_elements:
                    e_type = elem[1]
                    data = elem[2]
                    if e_type == 'header':
                        output_lines.append(f"\n\n**{data}**\n")
                    elif e_type == 'table':
                        table_rows = []
                        for row in data:
                            if not row or not any(row): continue
                            cleaned_cells = []
                            for idx, cell in enumerate(row):
                                cell_str = str(cell).replace('\n', ' ') if cell else ''
                                cell_str = re.sub(r'\s+', ' ', cell_str).strip()
                                
                                # If this cell contains comma-separated keywords/values, perform deduplication
                                if idx >= 1 and ',' in cell_str:
                                    terms = [t.strip() for t in cell_str.split(',')]
                                    dedup_terms = []
                                    seen_lower = set()
                                    for t in terms:
                                        t_clean = t.strip()
                                        if t_clean:
                                            key = t_clean.lower().strip('"\'')
                                            if key not in seen_lower:
                                                seen_lower.add(key)
                                                dedup_terms.append(t_clean)
                                    cell_str = ', '.join(dedup_terms)
                                
                                cleaned_cells.append(cell_str)
                            
                            if any(cleaned_cells):
                                table_rows.append(cleaned_cells)
                        
                        if table_rows:
                            first_row = table_rows[0]
                            is_header_row = any(h.lower() in ('topic', 'keywords', 'header') for h in first_row)
                            
                            num_cols = max(len(r) for r in table_rows)
                            
                            if is_header_row:
                                headers = first_row
                                start_idx = 1
                            else:
                                headers = [f"Col {i+1}" for i in range(num_cols)]
                                start_idx = 0
                            
                            # Emit header if not currently continuing a markdown table
                            if is_header_row or len(output_lines) == 0 or not output_lines[-1].startswith('|'):
                                hdr_line = "| " + " | ".join(headers) + " |"
                                sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
                                output_lines.append(hdr_line)
                                output_lines.append(sep_line)
                            
                            for r in table_rows[start_idx:]:
                                while len(r) < num_cols:
                                    r.append('')
                                output_lines.append("| " + " | ".join(r) + " |")

        if output_lines:
            return '\n'.join(output_lines).strip()
    except Exception as e:
        print(f"pdfplumber extraction notice: {e}")

    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(content))
        page_texts = []
        for page in reader.pages:
            try:
                txt = page.extract_text(extraction_mode="layout")
            except Exception:
                txt = page.extract_text()
            if txt and txt.strip():
                page_texts.append(txt)
        return "\n\n".join(page_texts)
    except Exception as e:
        return f"PDF Extraction Error: {str(e)}"


@router.post("/companies/{id}/upload-doc", response_model=CompanyOut, dependencies=[Depends(get_admin_user)])
async def upload_supporting_doc(id: int, file: UploadFile = File(...), db: AsyncSession = Depends(get_db_yield)):
    res = await db.execute(select(RobustCompany).where(RobustCompany.id == id))
    company = res.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    content = await file.read()
    extracted_text = ""
    filename = file.filename or "supporting_doc.pdf"

    if filename.lower().endswith(".pdf"):
        extracted_text = _smart_extract_pdf_content(content)
    else:
        try:
            extracted_text = content.decode("utf-8", errors="ignore")
        except Exception:
            raise HTTPException(status_code=400, detail="Unsupported document format. Please upload PDF or text file.")

    if not extracted_text.strip():
        raise HTTPException(status_code=400, detail="The uploaded document appears to be empty or unreadable text.")

    company.verification_doc_filename = filename
    company.verification_doc_text = extracted_text.strip()
    company.verification_doc_data = content
    await db.commit()
    await db.refresh(company)
    return await _build_company_out(company, db)


@router.get("/companies/{id}/doc/file", dependencies=[Depends(get_admin_user)])
async def get_supporting_doc_file(id: int, db: AsyncSession = Depends(get_db_yield)):
    res = await db.execute(select(RobustCompany).where(RobustCompany.id == id))
    company = res.scalar_one_or_none()
    if not company or not company.verification_doc_data:
        raise HTTPException(status_code=404, detail="Supporting document binary file not found")

    filename = company.verification_doc_filename or "document.pdf"
    media_type = "application/pdf" if filename.lower().endswith(".pdf") else "text/plain"
    
    from fastapi import Response
    return Response(
        content=company.verification_doc_data,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'}
    )


@router.delete("/companies/{id}/doc", response_model=CompanyOut, dependencies=[Depends(get_admin_user)])
async def delete_supporting_doc(id: int, db: AsyncSession = Depends(get_db_yield)):
    res = await db.execute(select(RobustCompany).where(RobustCompany.id == id))
    company = res.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    company.verification_doc_filename = None
    company.verification_doc_text = None
    company.verification_doc_data = None
    await db.commit()
    await db.refresh(company)
    return await _build_company_out(company, db)


@router.get("/companies/{id}/prompt-history", response_model=List[PromptHistoryOut], dependencies=[Depends(get_admin_user)])
async def get_prompt_history(id: int, db: AsyncSession = Depends(get_db_yield)):
    res = await db.execute(
        select(RobustPromptHistory)
        .where(RobustPromptHistory.company_id == id)
        .order_by(desc(RobustPromptHistory.created_at))
    )
    items = res.scalars().all()
    return [
        PromptHistoryOut(
            id=item.id,
            company_id=item.company_id,
            stage=item.stage,
            system_prompt=item.system_prompt,
            user_prompt=item.user_prompt,
            version_note=item.version_note,
            created_at=_fmt_dt(item.created_at) or "",
            created_by=item.created_by or "Admin"
        )
        for item in items
    ]


@router.post("/companies/{id}/restore-prompt", response_model=CompanyOut, dependencies=[Depends(get_admin_user)])
async def restore_prompt_version(id: int, body: RestorePromptIn, db: AsyncSession = Depends(get_db_yield)):
    res = await db.execute(select(RobustCompany).where(RobustCompany.id == id))
    company = res.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    h_res = await db.execute(select(RobustPromptHistory).where(RobustPromptHistory.id == body.history_id, RobustPromptHistory.company_id == id))
    hist = h_res.scalar_one_or_none()
    if not hist:
        raise HTTPException(status_code=404, detail="Prompt history entry not found")

    if hist.stage == "verification":
        company.verification_system_prompt = hist.system_prompt
        company.verification_user_prompt = hist.user_prompt
    elif hist.stage == "summary":
        company.summary_user_prompt = hist.user_prompt
    elif hist.stage == "executive":
        company.executive_user_prompt = hist.user_prompt

    # Create new history entry marking restore action
    new_hist = RobustPromptHistory(
        company_id=id,
        stage=hist.stage,
        system_prompt=hist.system_prompt,
        user_prompt=hist.user_prompt,
        version_note=f"Restored from version #{hist.id}",
        created_by="Admin"
    )
    db.add(new_hist)

    await db.commit()
    await db.refresh(company)
    return await _build_company_out(company, db)


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


