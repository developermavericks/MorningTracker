import asyncio
import sys
import os
from datetime import date
from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv()

from db.database import get_db, ScrapeJob
from scraper.engine import run_scrape_job

async def test_run():
    job_id = "a31a3421-6e1e-4384-b61c-4506e7486d45"
    sector = "Google"
    region = "india"
    date_from = date(2026, 3, 13)
    date_to = date(2026, 3, 14)
    search_mode = "broad"
    user_id = "test-user" # Or actual user ID

    print(f"Directly triggering run_scrape_job for {job_id}...")
    result = await run_scrape_job(job_id, sector, region, date_from, date_to, search_mode, user_id)
    print(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(test_run())
