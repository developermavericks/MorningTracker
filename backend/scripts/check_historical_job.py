import os
import sys
import asyncio

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import get_db, HistoricalJob, HistoricalSubJob
from sqlalchemy import select

async def check():
    async with get_db() as db:
        res_jobs = await db.execute(select(HistoricalJob))
        jobs = res_jobs.scalars().all()
        print("=== HISTORICAL JOBS STATUS ===")
        for j in jobs:
            print(f"Job Name: {j.name}")
            print(f"ID: {j.id} | Status: {j.status} | Completed Sub-Jobs: {j.completed_sub_jobs}/{j.total_sub_jobs} | Total Articles: {j.total_articles}")
            print(f"Master Excel Path: {j.master_excel_path}")
            
            res_subs = await db.execute(select(HistoricalSubJob).where(HistoricalSubJob.parent_job_id == j.id))
            subs = res_subs.scalars().all()
            for s in subs:
                print(f"   [Sub-Job] {s.id}: Window #{s.window_index} ({s.date_from} to {s.date_to}) | Status: {s.status} | Found: {s.articles_found} | Excel: {s.excel_file_path}")

if __name__ == "__main__":
    asyncio.run(check())
