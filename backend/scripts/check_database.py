import asyncio
import sys
import os
from sqlalchemy import select, func

# Add backend to path
sys.path.append(os.getcwd())

from db.database import get_db, ScrapeJob, Article

async def check_db():
    print("Database State Audit:")
    async with get_db() as db:
        # Total articles
        res = await db.execute(select(func.count(Article.id)))
        total_articles = res.scalar()
        print(f"  Total Articles in DB: {total_articles}")
        
        # Recent jobs
        res = await db.execute(select(ScrapeJob).order_by(ScrapeJob.started_at.desc()).limit(5))
        jobs = res.scalars().all()
        if jobs:
            print(f"  Recent Jobs:")
            for job in jobs:
                print(f"    - ID: {job.id} | Status: {job.status} | Found: {job.total_found} | Started: {job.started_at}")
        else:
            print("  No scrape jobs found.")

if __name__ == "__main__":
    asyncio.run(check_db())
