import os
import sys
import uuid
import asyncio
from datetime import date, datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import init_db, get_db, HistoricalJob, HistoricalSubJob, User
from sqlalchemy import select
from celery_app import app as celery_app

KEYWORDS = [
    "Emeritus",
    "Eruditus",
    "Ashwin Damera",
    "Chaitanya Kalipatnapu",
    "Bhushan Heda",
    "Avnish Singhal",
    "Jawahir Morarji"
]

async def trigger_eruditus_historical_job():
    date_from = date(2024, 10, 1)
    date_to = date(2024, 10, 7)
    job_name = "Eruditus / Emeritus 1-Week Backfill (Oct 1 - Oct 7, 2024)"

    print(f"Triggering Historical Automation Job: '{job_name}'...")
    print(f"Date Range: {date_from} to {date_to}")

    await init_db()

    async with get_db() as db:
        # Find default user or admin
        res_user = await db.execute(select(User).limit(1))
        user = res_user.scalar_one_or_none()
        if not user:
            user = User(id="admin_system", email="admin@mavericks.ai", name="System Admin", is_admin=True)
            db.add(user)
            await db.commit()

        user_id = user.id
        parent_job_id = f"hist_{uuid.uuid4().hex[:12]}"
        now = datetime.now()

        # Create parent job
        parent_job = HistoricalJob(
            id=parent_job_id,
            name=job_name,
            keywords=", ".join(KEYWORDS),
            date_from=date_from,
            date_to=date_to,
            window_days=7,
            status="running",
            total_sub_jobs=1,
            completed_sub_jobs=0,
            total_articles=0,
            user_id=user_id,
            started_at=now
        )
        db.add(parent_job)

        # Create 1-week sub-job
        sub_id = f"sub_{uuid.uuid4().hex[:12]}"
        sub_job = HistoricalSubJob(
            id=sub_id,
            parent_job_id=parent_job_id,
            window_index=1,
            date_from=date_from,
            date_to=date_to,
            status="pending"
        )
        db.add(sub_job)
        await db.commit()

        print(f"Created Parent Job '{parent_job_id}' and Sub-Job '{sub_id}' in Database.")

        # Dispatch task to Celery
        celery_app.send_task(
            "scraper.tasks.run_historical_sub_job_task",
            args=[parent_job_id, sub_id]
        )
        print(f"Dispatched Celery task 'run_historical_sub_job_task' for sub-job {sub_id}!")

if __name__ == "__main__":
    asyncio.run(trigger_eruditus_historical_job())
