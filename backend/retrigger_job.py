import asyncio
import os
from dotenv import load_dotenv
from sqlalchemy import select, update
from db.database import get_db, ScrapeJob
from celery_app import celery_app

# Load .env explicitly
load_dotenv()

async def find_and_retrigger():
    async with get_db() as db:
        print(f"Using DB: {os.getenv('DATABASE_URL')}")
        # Search for the job ID f8de1aae...
        res = await db.execute(select(ScrapeJob).where(ScrapeJob.id.like("f8de1aae%")))
        jobs = res.scalars().all()
        
        if not jobs:
            print("Job f8de1aae NOT FOUND in Postgres. Checking for any GOOGLE job...")
            res = await db.execute(select(ScrapeJob).where(ScrapeJob.sector.ilike("%google%")))
            jobs = res.scalars().all()

        if not jobs:
            print("No matching job found. Listing all jobs in Postgres:")
            res = await db.execute(select(ScrapeJob).order_by(ScrapeJob.started_at.desc()).limit(10))
            jobs = res.scalars().all()

        for job in jobs:
            print(f"JOB {job.id} | Status: {job.status} | Sector: {job.sector}")
            if job.status in ['pending', 'interrupted', 'running']:
                print(f"  ➜ Re-triggering Job {job.id}...")
                await db.execute(update(ScrapeJob).where(ScrapeJob.id == job.id).values(status='pending', current_phase='Preflight'))
                await db.commit()
                
                celery_app.send_task(
                    "scraper.tasks.run_scrape_task",
                    args=[job.id, job.sector, job.region, str(job.date_from), str(job.date_to), job.search_mode, job.user_id]
                )
                print("  ➜ Dispatched.")

if __name__ == "__main__":
    asyncio.run(find_and_retrigger())
