import asyncio
from sqlalchemy import select
from db.database import get_db, ScrapeJob

async def find_job():
    async with get_db() as db:
        res = await db.execute(select(ScrapeJob).order_by(ScrapeJob.started_at.desc()))
        jobs = res.scalars().all()
        print(f"Total jobs: {len(jobs)}")
        for job in jobs:
            print(f"JOB {job.id} | Status: {job.status} | Sector: {job.sector} | Region: {job.region}")

if __name__ == "__main__":
    asyncio.run(find_job())
