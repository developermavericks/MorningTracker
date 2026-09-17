import os
import uuid
import sys
import asyncio
from datetime import date, datetime, timedelta

# Add backend directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from celery_app import app as celery_app
from db.database import get_db, ScrapeJob, WatchedBrand, User
from sqlalchemy import select

# Target Keywords for Eruditus / Emeritus
KEYWORDS = [
    "Emeritus",
    "Eruditus",
    "Ashwin Damera",
    "Chaitanya Kalipatnapu",
    "Bhushan Heda",
    "Avnish Singhal",
    "Jawahir Morarji"
]

BRAND_NAME = "Eruditus / Emeritus"

async def backfill_emeritus_articles(start_date: date = date(2024, 10, 1), end_date: date = None):
    if end_date is None:
        end_date = date.today()

    print(f"=== Starting Historical Backfill for '{BRAND_NAME}' ===")
    print(f"Keywords: {', '.join(KEYWORDS)}")
    print(f"Date Range: {start_date} to {end_date}")

    async with get_db() as db:
        # 1. Get or create admin/system user
        res_user = await db.execute(select(User).limit(1))
        user = res_user.scalar_one_or_none()
        if not user:
            print("Creating default admin user for backfill...")
            user = User(id="admin_system", email="admin@mavericks.ai", name="System Admin", is_admin=True)
            db.add(user)
            await db.commit()

        user_id = user.id

        # 2. Ensure WatchedBrand exists with these keywords
        res_brand = await db.execute(
            select(WatchedBrand).where(WatchedBrand.name == BRAND_NAME).where(WatchedBrand.user_id == user_id)
        )
        brand_obj = res_brand.scalar_one_or_none()
        if not brand_obj:
            brand_obj = WatchedBrand(
                id=str(uuid.uuid4()),
                name=BRAND_NAME,
                keywords=", ".join(KEYWORDS),
                user_id=user_id
            )
            db.add(brand_obj)
            await db.commit()
            print(f"Registered WatchedBrand '{BRAND_NAME}' in database.")
        else:
            brand_obj.keywords = ", ".join(KEYWORDS)
            await db.commit()
            print(f"Updated WatchedBrand '{BRAND_NAME}' keywords in database.")

        # 3. Chunk date range into 15-day blocks to ensure optimal worker execution
        current_start = start_date
        job_ids = []

        while current_start <= end_date:
            current_end = min(current_start + timedelta(days=14), end_date)
            job_id = str(uuid.uuid4())

            new_job = ScrapeJob(
                id=job_id,
                sector=BRAND_NAME,
                region="india",
                user_id=user_id,
                date_from=current_start,
                date_to=current_end,
                status="pending",
                search_mode="broad",
                started_at=datetime.now()
            )
            db.add(new_job)
            await db.commit()

            # Dispatch Celery scrape task
            celery_app.send_task(
                "scraper.tasks.run_scrape_task",
                args=[job_id, BRAND_NAME, "india", str(current_start), str(current_end), "broad", user_id]
            )
            print(f"Dispatched Job {job_id} for period {current_start} to {current_end}")
            job_ids.append(job_id)

            current_start = current_end + timedelta(days=1)

    print(f"\nSuccessfully dispatched {len(job_ids)} scrape sub-jobs across the date range!")
    print("All tasks are now processing in Celery on Railway.")

if __name__ == "__main__":
    asyncio.run(backfill_emeritus_articles())
