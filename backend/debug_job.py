import asyncio
from sqlalchemy import select, func
from db.database import get_db, ScrapeJob, Article

async def debug():
    async with get_db() as db:
        res = await db.execute(select(ScrapeJob).where(ScrapeJob.id.like("b5f68ff3%")))
        jobs = res.scalars().all()
        if not jobs:
            print("Job b5f68ff3 NOT FOUND. Listing all pending/interrupted:")
            res = await db.execute(select(ScrapeJob).where(ScrapeJob.status.in_(["pending", "interrupted", "running"])).limit(20))
            jobs = res.scalars().all()
            
        for job in jobs:
            print(f"JOB {job.id}:")
            print(f"  Status: {job.status}")
            print(f"  Sector: {job.sector}")
            print(f"  Region: {job.region}")
            print(f"  Dates: {job.date_from} to {job.date_to}")
            print(f"  Phase: {job.current_phase}")
            print(f"  Found: {job.total_found}")
            print(f"  Scraped: {job.total_scraped}")
            print("-" * 20)

if __name__ == "__main__":
    asyncio.run(debug())
