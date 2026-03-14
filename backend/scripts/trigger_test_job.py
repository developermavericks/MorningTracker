import os
import uuid
import sys
from datetime import date, timedelta

# Add backend to path
sys.path.append(os.getcwd())

from celery_app import celery_app
from db.database import init_db, get_db, ScrapeJob, User
import asyncio

async def trigger_test_job():
    print("Triggering enterprise-scale discovery job...")
    
    # Selection
    sector = "technology"
    region = "india"
    yesterday = date.today() - timedelta(days=1)
    
    # 1. Ensure a user exists (or use system user)
    async with get_db() as db:
        from sqlalchemy import select
        res = await db.execute(select(User).limit(1))
        user = res.scalar_one_or_none()
        if not user:
            print("Creating test user...")
            user = User(id="test_user", email="test@example.com", name="Test User")
            db.add(user)
            await db.commit()
        
        user_id = user.id
        
        # 2. Create Job in DB
        job_id = str(uuid.uuid4())
        new_job = ScrapeJob(
            id=job_id,
            sector=sector,
            region=region,
            user_id=user_id,
            date_from=yesterday,
            date_to=yesterday,
            status='pending',
            search_mode='broad'
        )
        db.add(new_job)
        await db.commit()
        print(f"Created Job {job_id} in database.")

    # 3. Send Task to Celery
    celery_app.send_task(
        "scraper.tasks.run_scrape_task",
        args=[job_id, sector, region, str(yesterday), str(yesterday), "broad", user_id]
    )
    print(f"Dispatched task to Celery node. Job ID: {job_id}")
    print(f"Check scraper.log or run 'python tests/enterprise_test.py' to monitor.")

if __name__ == "__main__":
    asyncio.run(trigger_test_job())
