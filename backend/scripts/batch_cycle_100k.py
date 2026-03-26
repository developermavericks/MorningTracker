import os
import sys
import asyncio
import logging
import uuid
from datetime import datetime, date, timedelta

# Ensure project root is in PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from db.database import get_db_sync, ScrapeJob, init_logged_tables
from scraper.engine import discover_articles_scaling, bulk_insert_placeholders
from scraper.tasks import scrape_article_node
from sqlalchemy import update

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BATCH-SCALE")

async def run_12h_cycle():
    """
    100k Articles/Day Scaling Orchestrator.
    Cycle:
    1. Discovery (30m)
    2. Extraction Burst (11h)
    3. Cleanup (30m)
    """
    logger.info("=== STARTING 100K SCALING BATCH CYCLE ===")
    
    # 1. Initialize DB for Scaling
    await init_logged_tables()
    
    job_id = f"batch_{date.today().isoformat()}_{uuid.uuid4().hex[:6]}"
    sectors = ["artificial intelligence", "sports", "business", "education", "politics"]
    
    with get_db_sync() as db:
        new_job = ScrapeJob(
            id=job_id,
            sector="Multi-Sector (Scaling)",
            region="India",
            date_from=date.today(),
            date_to=date.today(),
            status="running",
            search_mode="scaling_burst",
            current_phase="Discovery"
        )
        db.add(new_job)
        db.commit()

    # 2. Discovery Phase (30m target)
    logger.info(f"PHASE 1: Discovery for sectors: {sectors}")
    discovered_articles = await discover_articles_scaling(job_id, sectors=sectors)
    
    if not discovered_articles:
        logger.warning("No new articles discovered. Ending cycle.")
        return

    # 3. Batch Placeholder Ingestion
    logger.info(f"PHASE 2: Ingesting {len(discovered_articles)} placeholders...")
    with get_db_sync() as db:
        bulk_insert_placeholders(db, job_id, discovered_articles, "Mixed", "India", "admin")
        db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(
            total_found=len(discovered_articles),
            current_phase="Extraction Burst"
        ))
        db.commit()

    # 4. Extraction Burst (11h target)
    logger.info(f"PHASE 3: Dispatching Extraction Nodes (Scaling Mode)...")
    for a in discovered_articles:
        # Dispatch with scaling_mode=True to enforce speed and skip browsers
        scrape_article_node.delay(a, job_id, a.get("sector", "Mixed"), "India", "admin", scaling_mode=True)
    
    logger.info(f"Dispatched {len(discovered_articles)} tasks to Celery cluster.")
    logger.info("PHASE 4: Monitoring Throughput (Target 2.3 articles/sec)...")
    
    # 5. Cleanup & Maintenance (scheduled separately or after completion)
    # At this scale, we leave workers to finish and rely on the next cycle to cleanup.
    logger.info("=== BATCH CYCLE ORCHESTRATED SUCCESSFULLY ===")

if __name__ == "__main__":
    asyncio.run(run_12h_cycle())
