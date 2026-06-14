import asyncio
import uuid
from datetime import date, datetime
from db.database import get_db, ScrapeJob
from celery_app import app as celery_app

async def test_high_priority_job():
    job_id = str(uuid.uuid4())
    user_id = 1 # Assuming admin or first user
    
    print(f"Starting test job: {job_id}")
    
    async with get_db() as db:
        new_job = ScrapeJob(
            id=job_id,
            sector="technology",
            region="united states",
            user_id=user_id,
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 15),
            status='pending',
            search_mode='broad',
            started_at=datetime.now()
        )
        db.add(new_job)
        await db.commit()
    
    # Dispatch using the new routing
    celery_app.send_task(
        "scraper.tasks.run_scrape_task",
        args=[job_id, "technology", "united states", "2026-03-01", "2026-03-15", "broad", user_id]
    )
    print(f"Task dispatched to orchestrator queue. Waiting for status change...")
    
    for _ in range(30):
        await asyncio.sleep(2)
        async with get_db() as db:
            from sqlalchemy import select
            res = await db.execute(select(ScrapeJob).where(ScrapeJob.id == job_id))
            job = res.scalar_one()
            print(f"Status: {job.status} | Found: {job.total_found} | Scraped: {job.total_scraped}")
            if job.status == 'running':
                print("SUCCESS: Orchestrator picked it up!")
                # break # Continue to see if articles start appearing
            if job.total_found > 0:
                print(f"SUCCESS: Found {job.total_found} articles!")
                break
    else:
        print("FAILED: Job stayed pending or didn't find articles.")

if __name__ == "__main__":
    asyncio.run(test_high_priority_job())
