import asyncio
import sys
import os
from datetime import datetime
from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv()

from db.database import get_db, ScrapeJob, Article
from sqlalchemy import select

async def check_all_jobs():
    async with get_db() as db:
        res = await db.execute(select(ScrapeJob).order_by(ScrapeJob.started_at.desc()).limit(20))
        jobs = res.scalars().all()
        
        if not jobs:
            print("No jobs found in the database.")
            return

        print(f"Listing last 20 jobs:")
        for job in jobs:
            print(f"ID: {job.id} | Status: {job.status} | Target: {job.sector} | Created: {job.started_at}")

if __name__ == "__main__":
    asyncio.run(check_all_jobs())
