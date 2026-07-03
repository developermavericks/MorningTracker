from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy import select, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, EmailStr
from typing import List, Optional
import os
import shutil
import logging

logger = logging.getLogger("clients")

from db.database import (
    get_db_yield, Client, ClientSection, ClientKeyword, 
    ClientRecipient, ClientRunLog, User
)
from .auth_utils import get_auth_user, TokenData
from celery_app import app as celery_app

router = APIRouter(prefix="/clients", tags=["clients"])

async def get_admin_user(current_user: TokenData = Depends(get_auth_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

# --- Pydantic Schemas ---
class SectionCreate(BaseModel):
    name: str
    keywords: List[str]

class ClientCreate(BaseModel):
    name: str
    scheduled_time: str = "07:00"
    timezone: str = "Asia/Kolkata"
    is_active: bool = True
    recipients: List[EmailStr]
    sections: List[SectionCreate]
    context: Optional[str] = None
    summary_length: int = 35

class SectionResponse(BaseModel):
    id: int
    name: str
    keywords: List[str]

class ClientResponse(BaseModel):
    id: int
    name: str
    scheduled_time: str
    timezone: str
    is_active: bool
    template_path: Optional[str]
    recipients: List[str]
    sections: List[SectionResponse]
    last_run_at: Optional[str] = None
    context: Optional[str] = None
    summary_length: int = 35

class RunLogResponse(BaseModel):
    id: int
    client_id: int
    status: str
    error_message: Optional[str]
    progress_message: Optional[str]
    generated_file_path: Optional[str]
    started_at: str
    completed_at: Optional[str]

# --- Router Endpoints ---

@router.get("/", response_model=List[ClientResponse])
async def list_clients(
    db: AsyncSession = Depends(get_db_yield),
    current_user: TokenData = Depends(get_admin_user)
):
    stmt = select(Client).order_by(Client.name)
    res = await db.execute(stmt)
    clients = res.scalars().all()
    
    response_data = []
    for client in clients:
        rec_stmt = select(ClientRecipient).where(ClientRecipient.client_id == client.id)
        rec_res = await db.execute(rec_stmt)
        recipients = [r.email for r in rec_res.scalars().all()]
        
        sec_stmt = select(ClientSection).where(ClientSection.client_id == client.id)
        sec_res = await db.execute(sec_stmt)
        sections = sec_res.scalars().all()
        
        sections_data = []
        for sec in sections:
            key_stmt = select(ClientKeyword).where(ClientKeyword.section_id == sec.id)
            key_res = await db.execute(key_stmt)
            keywords = [k.keyword for k in key_res.scalars().all()]
            
            sections_data.append(
                SectionResponse(
                    id=sec.id,
                    name=sec.name,
                    keywords=keywords
                )
            )
            
        response_data.append(
            ClientResponse(
                id=client.id,
                name=client.name,
                scheduled_time=client.scheduled_time,
                timezone=client.timezone,
                is_active=client.is_active,
                template_path=client.template_path,
                recipients=recipients,
                sections=sections_data,
                last_run_at=client.last_run_at.isoformat() + ("Z" if client.last_run_at.tzinfo is None else "") if client.last_run_at else None,
                context=client.context,
                summary_length=client.summary_length or 35
            )
        )
    return response_data

@router.post("/", response_model=ClientResponse)
async def create_client(
    payload: ClientCreate,
    db: AsyncSession = Depends(get_db_yield),
    current_user: TokenData = Depends(get_admin_user)
):
    exist_stmt = select(Client).where(Client.name == payload.name)
    exist_res = await db.execute(exist_stmt)
    if exist_res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Client with this name already exists")
        
    new_client = Client(
        name=payload.name,
        scheduled_time=payload.scheduled_time,
        timezone=payload.timezone,
        is_active=payload.is_active,
        context=payload.context,
        summary_length=payload.summary_length
    )
    db.add(new_client)
    await db.commit()
    await db.refresh(new_client)
    
    # Save recipients
    for email in payload.recipients:
        rec = ClientRecipient(client_id=new_client.id, email=email)
        db.add(rec)
        
    # Save sections and keywords
    sections_response = []
    for sec_data in payload.sections:
        sec = ClientSection(client_id=new_client.id, name=sec_data.name)
        db.add(sec)
        await db.commit()
        await db.refresh(sec)
        
        for kw in sec_data.keywords:
            if kw.strip():
                kwd = ClientKeyword(section_id=sec.id, keyword=kw.strip())
                db.add(kwd)
                
        sections_response.append(
            SectionResponse(
                id=sec.id,
                name=sec.name,
                keywords=sec_data.keywords
            )
        )
        
    await db.commit()
    
    return ClientResponse(
        id=new_client.id,
        name=new_client.name,
        scheduled_time=new_client.scheduled_time,
        timezone=new_client.timezone,
        is_active=new_client.is_active,
        template_path=None,
        recipients=payload.recipients,
        sections=sections_response,
        last_run_at=None,
        context=new_client.context,
        summary_length=new_client.summary_length
    )

@router.put("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: int,
    payload: ClientCreate,
    db: AsyncSession = Depends(get_db_yield),
    current_user: TokenData = Depends(get_admin_user)
):
    stmt = select(Client).where(Client.id == client_id)
    res = await db.execute(stmt)
    client = res.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
        
    client.name = payload.name
    client.scheduled_time = payload.scheduled_time
    client.timezone = payload.timezone
    client.is_active = payload.is_active
    client.context = payload.context
    client.summary_length = payload.summary_length
    
    # Update recipients (clear old first)
    await db.execute(delete(ClientRecipient).where(ClientRecipient.client_id == client_id))
    for email in payload.recipients:
        rec = ClientRecipient(client_id=client_id, email=email)
        db.add(rec)
        
    # Update sections and keywords (clear old first)
    sec_ids_stmt = select(ClientSection.id).where(ClientSection.client_id == client_id)
    sec_ids_res = await db.execute(sec_ids_stmt)
    sec_ids = sec_ids_res.scalars().all()
    if sec_ids:
        await db.execute(delete(ClientKeyword).where(ClientKeyword.section_id.in_(sec_ids)))
    await db.execute(delete(ClientSection).where(ClientSection.client_id == client_id))
    
    sections_response = []
    for sec_data in payload.sections:
        sec = ClientSection(client_id=client_id, name=sec_data.name)
        db.add(sec)
        await db.commit()
        await db.refresh(sec)
        
        for kw in sec_data.keywords:
            if kw.strip():
                kwd = ClientKeyword(section_id=sec.id, keyword=kw.strip())
                db.add(kwd)
                
        sections_response.append(
            SectionResponse(
                id=sec.id,
                name=sec.name,
                keywords=sec_data.keywords
            )
        )
        
    await db.commit()
    await db.refresh(client)
    
    return ClientResponse(
        id=client.id,
        name=client.name,
        scheduled_time=client.scheduled_time,
        timezone=client.timezone,
        is_active=client.is_active,
        template_path=client.template_path,
        recipients=payload.recipients,
        sections=sections_response,
        last_run_at=client.last_run_at.isoformat() + ("Z" if client.last_run_at.tzinfo is None else "") if client.last_run_at else None,
        context=client.context,
        summary_length=client.summary_length or 35
    )

@router.delete("/{client_id}")
async def delete_client(
    client_id: int,
    db: AsyncSession = Depends(get_db_yield),
    current_user: TokenData = Depends(get_admin_user)
):
    stmt = select(Client).where(Client.id == client_id)
    res = await db.execute(stmt)
    client = res.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
        
    if client.template_path:
        templates_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
        resolved_path = os.path.join(templates_dir, os.path.basename(client.template_path))
        if os.path.exists(resolved_path):
            try:
                os.remove(resolved_path)
            except Exception:
                pass
            
    await db.execute(delete(Client).where(Client.id == client_id))
    await db.commit()
    return {"detail": "Client deleted successfully"}

@router.post("/{client_id}/template")
async def upload_template(
    client_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_yield),
    current_user: TokenData = Depends(get_admin_user)
):
    stmt = select(Client).where(Client.id == client_id)
    res = await db.execute(stmt)
    client = res.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
        
    if not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only .docx template files are allowed")
        
    templates_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
    os.makedirs(templates_dir, exist_ok=True)
    
    filename = f"client_{client_id}_template.docx"
    file_path = os.path.join(templates_dir, filename)
    
    # Read file bytes and save to database
    file_bytes = await file.read()
    client.template_data = file_bytes
    client.template_path = filename
    
    # Write to local cache path
    with open(file_path, "wb") as buffer:
        buffer.write(file_bytes)
        
    await db.commit()
    
    return {"detail": "Template uploaded successfully", "path": file_path}

@router.get("/{client_id}/template")
async def download_template(
    client_id: int,
    db: AsyncSession = Depends(get_db_yield),
    current_user: TokenData = Depends(get_admin_user)
):
    stmt = select(Client).where(Client.id == client_id)
    res = await db.execute(stmt)
    client = res.scalar_one_or_none()
    if not client or not client.template_path:
        raise HTTPException(status_code=404, detail="Template not found")
        
    templates_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
    os.makedirs(templates_dir, exist_ok=True)
    file_path = os.path.join(templates_dir, os.path.basename(client.template_path))
    
    # Restore from database if missing on disk (critical for container rebuilding/ephemeral storage)
    if client.template_data and not os.path.exists(file_path):
        try:
            with open(file_path, "wb") as buffer:
                buffer.write(client.template_data)
        except Exception as e:
            logger.error(f"Failed to restore template from database: {e}")
            
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Template file not found on disk")
        
    return FileResponse(
        path=file_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=os.path.basename(client.template_path)
    )

@router.delete("/{client_id}/template")
async def delete_template(
    client_id: int,
    db: AsyncSession = Depends(get_db_yield),
    current_user: TokenData = Depends(get_admin_user)
):
    stmt = select(Client).where(Client.id == client_id)
    res = await db.execute(stmt)
    client = res.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
        
    if client.template_path:
        templates_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
        file_path = os.path.join(templates_dir, os.path.basename(client.template_path))
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        client.template_path = None
        await db.commit()
        
    return {"detail": "Template deleted successfully"}

@router.get("/{client_id}/logs", response_model=List[RunLogResponse])
async def get_client_run_logs(
    client_id: int,
    db: AsyncSession = Depends(get_db_yield),
    current_user: TokenData = Depends(get_admin_user)
):
    stmt = select(ClientRunLog).where(ClientRunLog.client_id == client_id).order_by(desc(ClientRunLog.started_at))
    res = await db.execute(stmt)
    logs = res.scalars().all()
    
    return [
        RunLogResponse(
            id=log.id,
            client_id=log.client_id,
            status=log.status,
            error_message=log.error_message,
            progress_message=log.progress_message,
            generated_file_path=(
                log.generated_file_path if (log.generated_file_path and log.generated_file_path.startswith("https://"))
                else (os.path.basename(log.generated_file_path) if log.generated_file_path else None)
            ),
            started_at=log.started_at.isoformat() + ("Z" if log.started_at.tzinfo is None else ""),
            completed_at=log.completed_at.isoformat() + ("Z" if log.completed_at.tzinfo is None else "") if log.completed_at else None
        )
        for log in logs
    ]

@router.post("/{client_id}/run")
async def trigger_client_run(
    client_id: int,
    db: AsyncSession = Depends(get_db_yield),
    current_user: TokenData = Depends(get_admin_user)
):
    stmt = select(Client).where(Client.id == client_id)
    res = await db.execute(stmt)
    client = res.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
        
    task = celery_app.send_task(
        "scraper.tasks.run_client_report_task",
        args=[client_id]
    )
    
    return {"detail": "Client report generation task triggered", "task_id": task.id}

from fastapi.responses import FileResponse

@router.get("/reports/{filename}")
async def download_report(
    filename: str,
    current_user: TokenData = Depends(get_admin_user)
):
    reports_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
    file_path = os.path.join(reports_dir, filename)
    
    real_path = os.path.realpath(file_path)
    real_reports_dir = os.path.realpath(reports_dir)
    if not real_path.startswith(real_reports_dir):
        raise HTTPException(status_code=403, detail="Access denied")
        
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    return FileResponse(
        file_path, 
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
        filename=filename
    )
