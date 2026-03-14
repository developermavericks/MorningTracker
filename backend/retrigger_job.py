import asyncio
import sys
import os
from dotenv import load_dotenv

# Add current directory to sys.path
sys.path.append(os.getcwd())
load_dotenv()

from db.database import get_db, ScrapeJob
from sqlalchemy import select
from celery_app import celery_app

async def retrigger_job(job_id):
    async with get_db() as db:
        res = await db.execute(select(ScrapeJob).where(ScrapeJob.id == job_id))
        job = res.scalar_one_or_none()
        
        if not job:
            print(f"Error: Job {job_id} not found.")
            return

        print(f"Retriggering Job: {job.id}")
        print(f"  Target: {job.sector} in {job.region}")
        print(f"  Dates: {job.date_from} to {job.date_to}")
        
        # Dispatch to Celery
        celery_app.send_task(
            "scraper.tasks.run_scrape_task",
            args=[
                job.id, 
                job.sector, 
                job.region, 
                str(job.date_from), 
                str(job.date_to), 
                job.search_mode, 
                job.user_id
            ]
        )
        print("Task dispatched to Celery.")

if __name__ == "__main__":
    job_id = "a31a3421-6e1e-4384-b61c-4506e7486d45"
    asyncio.run(retrigger_job(job_id))
