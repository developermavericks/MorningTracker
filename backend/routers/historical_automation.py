import os
import uuid
import logging
from datetime import date, datetime, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, update, delete, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import (
    get_db_yield, HistoricalJob, HistoricalSubJob, HistoricalArticle
)
from .auth_utils import get_auth_user, TokenData
from celery_app import app as celery_app

router = APIRouter(prefix="/historical-automation", tags=["historical-automation"])

class HistoricalJobCreate(BaseModel):
    name: str
    keywords: str
    date_from: date
    date_to: date
    window_days: int = 15
    resolve_urls: bool = False

CLIENT_HISTORICAL_PRESETS = [
    {
        "id": "eruditus",
        "name": "Eruditus / Emeritus Backfill",
        "keywords": "Emeritus, Eruditus, Ashwin Damera, Chaitanya Kalipatnapu, Bhushan Heda, Avnish Singhal, Jawahir Morarji",
        "window_days": 15
    },
    {
        "id": "google",
        "name": "Google India Backfill",
        "keywords": "\"Google India\", \"Sundar Pichai\", Google Pay + India, Google Cloud + India, YouTube + India, Google AI",
        "window_days": 15
    },
    {
        "id": "protectt_ai",
        "name": "Protectt.ai Security Backfill",
        "keywords": "\"Protectt.ai\", \"mobile threat defense\", App Protection - gaming, RASP security, cybersecurity + banking",
        "window_days": 15
    },
    {
        "id": "scapia",
        "name": "Scapia Cards Backfill",
        "keywords": "Scapia, \"Scapia Federal Credit Card\", travel credit card + India, Anil Goteti",
        "window_days": 15
    },
    {
        "id": "wadhwani_ai",
        "name": "Wadhwani AI Healthcare Backfill",
        "keywords": "\"Wadhwani AI\", AI + healthcare + India, maternal health + AI, pest management + AI",
        "window_days": 15
    },
    {
        "id": "murf_ai",
        "name": "Murf AI Backfill",
        "keywords": "\"Murf AI\", \"voice generator\", text to speech + AI, Ankur Edkie",
        "window_days": 15
    }
]

@router.get("/client-presets")
async def get_client_presets():
    """Returns available client historical automation presets."""
    return {"presets": CLIENT_HISTORICAL_PRESETS}


def calculate_monthly_summary(sub_jobs: List[HistoricalSubJob]) -> List[dict]:
    """Generates month-by-month status badges for the monthly tracker."""
    months = {}
    for sj in sub_jobs:
        if not sj.date_from:
            continue
        try:
            m_key = sj.date_from.strftime("%b %Y") if hasattr(sj.date_from, 'strftime') else str(sj.date_from)[:7]
        except Exception:
            m_key = "Unknown Month"

        if m_key not in months:
            months[m_key] = {"month": m_key, "completed": 0, "total": 0, "statuses": set()}
        months[m_key]["total"] += 1
        months[m_key]["statuses"].add(sj.status)
        if sj.status == "completed":
            months[m_key]["completed"] += 1

    summary = []
    for m_key, data in months.items():
        statuses = data["statuses"]
        if "running" in statuses:
            final_status = "running"
        elif "paused" in statuses:
            final_status = "paused"
        elif data["completed"] == data["total"]:
            final_status = "completed"
        elif "cancelled" in statuses:
            final_status = "cancelled"
        else:
            final_status = "pending"

        summary.append({
            "month": m_key,
            "status": final_status,
            "completed_windows": data["completed"],
            "total_windows": data["total"]
        })
    return summary

def calculate_eta(job: HistoricalJob, sub_jobs: List[HistoricalSubJob]) -> dict:
    """Calculates elapsed time and dynamic ETA in seconds based on completed windows."""
    now = datetime.now()
    started = job.started_at or now
    elapsed_seconds = int((now - started).total_seconds())

    completed_jobs = [sj for sj in sub_jobs if sj.status == "completed" and sj.started_at and sj.completed_at]
    remaining_count = sum(1 for sj in sub_jobs if sj.status in ("pending", "running"))

    if not completed_jobs or remaining_count == 0:
        eta_seconds = 0
    else:
        durations = [(sj.completed_at - sj.started_at).total_seconds() for sj in completed_jobs]
        avg_duration = sum(durations) / len(durations)
        eta_seconds = int(avg_duration * remaining_count)

    return {
        "elapsed_seconds": elapsed_seconds,
        "eta_seconds": eta_seconds
    }


@router.post("/start")
async def start_historical_job(
    req: HistoricalJobCreate,
    db: AsyncSession = Depends(get_db_yield),
    current_user: TokenData = Depends(get_auth_user)
):
    """Starts a fast historical metadata scrape with auto 15-day window slicing."""
    if req.date_from > req.date_to:
        raise HTTPException(400, "Start date cannot be after end date")

    if req.window_days < 1:
        raise HTTPException(400, "Window days must be at least 1")

    # Generate 15-day sub-window ranges
    windows = []
    curr = req.date_from
    while curr <= req.date_to:
        w_end = min(curr + timedelta(days=req.window_days - 1), req.date_to)
        windows.append((curr, w_end))
        curr = w_end + timedelta(days=1)

    parent_job_id = f"hist_{uuid.uuid4().hex[:12]}"
    now = datetime.now()

    new_parent = HistoricalJob(
        id=parent_job_id,
        name=req.name.strip(),
        keywords=req.keywords.strip(),
        date_from=req.date_from,
        date_to=req.date_to,
        window_days=req.window_days,
        status="running",
        total_sub_jobs=len(windows),
        completed_sub_jobs=0,
        total_articles=0,
        user_id=current_user.id,
        resolve_urls=req.resolve_urls,
        started_at=now
    )
    db.add(new_parent)

    sub_job_ids = []
    for idx, (w_start, w_end) in enumerate(windows, 1):
        sub_id = f"sub_{uuid.uuid4().hex[:12]}"
        sub_job = HistoricalSubJob(
            id=sub_id,
            parent_job_id=parent_job_id,
            window_index=idx,
            date_from=w_start,
            date_to=w_end,
            status="pending"
        )
        db.add(sub_job)
        sub_job_ids.append(sub_id)

    await db.commit()

    # Dispatch Celery sub-tasks
    for sub_id in sub_job_ids:
        celery_app.send_task(
            "scraper.tasks.run_historical_sub_job_task",
            args=[parent_job_id, sub_id]
        )

    return {
        "job_id": parent_job_id,
        "total_sub_jobs": len(windows),
        "status": "running"
    }


@router.get("/jobs")
async def list_historical_jobs(
    response: Response,
    sort_by: str = "created_at",
    order: str = "desc",
    db: AsyncSession = Depends(get_db_yield),
    current_user: TokenData = Depends(get_auth_user)
):
    """Lists historical jobs with ETA metrics, month trackers, and sub-process counts."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"

    query = select(HistoricalJob)
    if sort_by == "date_from":
        query = query.order_by(asc(HistoricalJob.date_from) if order == "asc" else desc(HistoricalJob.date_from))
    else:
        query = query.order_by(asc(HistoricalJob.started_at) if order == "asc" else desc(HistoricalJob.started_at))

    res = await db.execute(query)
    jobs = res.scalars().all()

    output = []
    for j in jobs:
        try:
            # Load sub-jobs to compute metrics
            res_subs = await db.execute(
                select(HistoricalSubJob)
                .where(HistoricalSubJob.parent_job_id == j.id)
                .order_by(HistoricalSubJob.window_index.asc())
            )
            subs = res_subs.scalars().all()

            eta_info = calculate_eta(j, subs)
            monthly_tracker = calculate_monthly_summary(subs)

            total_duration = int((j.completed_at - j.started_at).total_seconds()) if (j.completed_at and j.started_at) else eta_info["elapsed_seconds"]

            j_dict = {
                "id": j.id,
                "name": j.name,
                "keywords": j.keywords,
                "date_from": str(j.date_from) if j.date_from else "",
                "date_to": str(j.date_to) if j.date_to else "",
                "window_days": j.window_days,
                "status": j.status,
                "total_sub_jobs": j.total_sub_jobs,
                "completed_sub_jobs": j.completed_sub_jobs,
                "total_articles": j.total_articles,
                "has_master_excel": bool(j.master_excel_path or j.status == "completed"),
                "started_at": j.started_at.isoformat() if j.started_at else None,
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
                "elapsed_seconds": eta_info["elapsed_seconds"],
                "eta_seconds": eta_info["eta_seconds"],
                "total_duration_seconds": total_duration,
                "monthly_tracker": monthly_tracker,
                "sub_jobs": [
                    {
                        "id": sj.id,
                        "window_index": sj.window_index,
                        "date_from": str(sj.date_from) if sj.date_from else "",
                        "date_to": str(sj.date_to) if sj.date_to else "",
                        "status": sj.status,
                        "articles_found": sj.articles_found,
                        "has_excel": bool(sj.excel_file_path or sj.status == "completed"),
                        "started_at": sj.started_at.isoformat() if sj.started_at else None,
                        "completed_at": sj.completed_at.isoformat() if sj.completed_at else None,
                        "execution_seconds": int((sj.completed_at - sj.started_at).total_seconds()) if (sj.started_at and sj.completed_at) else None
                    }
                    for sj in subs
                ]
            }
            output.append(j_dict)
        except Exception as job_err:
            logger.error(f"Error formatting historical job {j.id}: {job_err}")

    return {"jobs": output}


@router.post("/jobs/{job_id}/stop")
async def stop_historical_job(
    job_id: str,
    db: AsyncSession = Depends(get_db_yield),
    current_user: TokenData = Depends(get_auth_user)
):
    """Stops/Pauses an entire parent job safely WITHOUT deleting any scraped articles or Excel files."""
    res = await db.execute(select(HistoricalJob).where(HistoricalJob.id == job_id))
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")

    await db.execute(
        update(HistoricalJob).where(HistoricalJob.id == job_id).values(status="paused")
    )
    await db.execute(
        update(HistoricalSubJob)
        .where(HistoricalSubJob.parent_job_id == job_id)
        .where(HistoricalSubJob.status.in_(["pending", "running"]))
        .values(status="paused")
    )
    await db.commit()

    return {"status": "paused", "job_id": job_id, "message": "Job paused safely. All scraped data preserved."}


@router.post("/sub-jobs/{sub_job_id}/stop")
async def stop_historical_sub_job(
    sub_job_id: str,
    db: AsyncSession = Depends(get_db_yield),
    current_user: TokenData = Depends(get_auth_user)
):
    """Stops/Pauses an individual 15-day sub-job safely WITHOUT deleting its data."""
    res = await db.execute(select(HistoricalSubJob).where(HistoricalSubJob.id == sub_job_id))
    sub = res.scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Sub-job not found")

    await db.execute(
        update(HistoricalSubJob).where(HistoricalSubJob.id == sub_job_id).values(status="paused")
    )
    await db.commit()

    return {"status": "paused", "sub_job_id": sub_job_id}


@router.delete("/jobs/{job_id}/data")
async def purge_historical_job_data(
    job_id: str,
    db: AsyncSession = Depends(get_db_yield),
    current_user: TokenData = Depends(get_auth_user)
):
    """Deletes all scraped articles and reset article counters for a job without deleting the job object."""
    res = await db.execute(select(HistoricalJob).where(HistoricalJob.id == job_id))
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")

    await db.execute(delete(HistoricalArticle).where(HistoricalArticle.parent_job_id == job_id))
    await db.execute(update(HistoricalJob).where(HistoricalJob.id == job_id).values(total_articles=0))
    await db.execute(update(HistoricalSubJob).where(HistoricalSubJob.parent_job_id == job_id).values(articles_found=0))
    await db.commit()

    return {"deleted_data_for": job_id}


@router.delete("/jobs/{job_id}")
async def delete_historical_job(
    job_id: str,
    keep_data: bool = False,
    db: AsyncSession = Depends(get_db_yield),
    current_user: TokenData = Depends(get_auth_user)
):
    """Deletes historical job and sub-jobs. If keep_data is True, scraped articles remain in database."""
    res = await db.execute(select(HistoricalJob).where(HistoricalJob.id == job_id))
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")

    if keep_data:
        # Unlink articles from job so they remain preserved in DB
        await db.execute(
            update(HistoricalArticle)
            .where(HistoricalArticle.parent_job_id == job_id)
            .values(parent_job_id=None, sub_job_id=None)
        )
    else:
        # Delete articles along with job
        await db.execute(delete(HistoricalArticle).where(HistoricalArticle.parent_job_id == job_id))

    await db.execute(delete(HistoricalSubJob).where(HistoricalSubJob.parent_job_id == job_id))
    await db.delete(job)
    await db.commit()

    return {"deleted_job": job_id, "keep_data": keep_data}



@router.get("/jobs/{job_id}/download")
async def download_master_excel(
    job_id: str,
    db: AsyncSession = Depends(get_db_yield),
    current_user: TokenData = Depends(get_auth_user)
):
    """Downloads the consolidated master cumulative Excel spreadsheet, dynamically regenerating if missing on web container."""
    res = await db.execute(select(HistoricalJob).where(HistoricalJob.id == job_id))
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Master job not found")

    from scraper.historical_engine import create_excel_report, REPORTS_DIR
    target_path = job.master_excel_path or os.path.join(REPORTS_DIR, f"historical_{job.id}_MASTER.xlsx")

    if not os.path.exists(target_path):
        # Dynamically regenerate Excel from DB records
        res_all = await db.execute(
            select(HistoricalArticle)
            .where(HistoricalArticle.parent_job_id == job_id)
            .order_by(HistoricalArticle.published_date.desc())
        )
        arts = [
            {
                "title": a.title,
                "publication": a.publication,
                "url": a.url,
                "published_date": a.published_date,
                "matched_keywords": a.matched_keywords
            } for a in res_all.scalars().all()
        ]
        master_title = f"{job.name} MASTER ({job.date_from} to {job.date_to})"
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        create_excel_report(target_path, master_title, arts)

    filename = f"{job.name}_Cumulative_Historical_Report.xlsx".replace(" ", "_")
    return FileResponse(
        path=target_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@router.get("/sub-jobs/{sub_job_id}/download")
async def download_sub_job_excel(
    sub_job_id: str,
    db: AsyncSession = Depends(get_db_yield),
    current_user: TokenData = Depends(get_auth_user)
):
    """Downloads the 15-day window Excel spreadsheet, dynamically regenerating if missing on web container."""
    res = await db.execute(select(HistoricalSubJob).where(HistoricalSubJob.id == sub_job_id))
    sub = res.scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "15-Day window sub-job not found")

    from scraper.historical_engine import create_excel_report, REPORTS_DIR
    target_path = sub.excel_file_path or os.path.join(REPORTS_DIR, f"historical_{sub.parent_job_id}_window_{sub.window_index}.xlsx")

    if not os.path.exists(target_path):
        # Dynamically regenerate Excel from DB records for this window
        res_arts = await db.execute(
            select(HistoricalArticle)
            .where(HistoricalArticle.sub_job_id == sub_job_id)
            .order_by(HistoricalArticle.published_date.desc())
        )
        arts = [
            {
                "title": a.title,
                "publication": a.publication,
                "url": a.url,
                "published_date": a.published_date,
                "matched_keywords": a.matched_keywords
            } for a in res_arts.scalars().all()
        ]
        res_parent = await db.execute(select(HistoricalJob).where(HistoricalJob.id == sub.parent_job_id))
        parent_job = res_parent.scalar_one_or_none()
        p_name = parent_job.name if parent_job else "Historical"
        title_text = f"{p_name} ({sub.date_from} to {sub.date_to})"
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        create_excel_report(target_path, title_text, arts)

    filename = f"Historical_Window_{sub.window_index}_{sub.date_from}_to_{sub.date_to}.xlsx"
    return FileResponse(
        path=target_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

