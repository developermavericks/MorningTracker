import asyncio
import sys
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Add current directory to sys.path
sys.path.append(os.getcwd())
load_dotenv()

from db.database import get_db, ScrapeJob, Article
from sqlalchemy import select

async def check_recent_jobs():
    async with get_db() as db:
        hour_ago = datetime.now() - timedelta(hours=1)
        res = await db.execute(select(ScrapeJob).where(ScrapeJob.started_at > hour_ago))
        jobs = res.scalars().all()
        
        if not jobs:
            print("No jobs found in the last hour.")
            return

        print(f"Found {len(jobs)} jobs in the last hour:")
        for job in jobs:
            print(f"ID: {job.id} | Status: {job.status} | Target: {job.sector} | Created: {job.started_at}")

if __name__ == "__main__":
    asyncio.run(check_recent_jobs())
