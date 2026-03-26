import os
import sys
import time
import psutil
import logging
from datetime import datetime, date

# Ensure project root is in PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from scraper.tasks import scrape_article_node
from db.database import get_db_sync, ScrapeJob

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("STRESS-TEST")

def run_stress_test(count=1000):
    """
    Stress tests the extraction engine by dispatching a burst of mock articles.
    Profiles RAM/CPU usage during the process.
    """
    logger.info(f"=== Starting Stress Test: {count} articles ===")
    
    job_id = f"stress_{int(time.time())}"
    with get_db_sync() as db:
        new_job = ScrapeJob(
            id=job_id,
            sector="Stress-Test",
            region="India",
            date_from=date.today(),
            date_to=date.today(),
            status="running",
            search_mode="scaling_burst",
            total_found=count
        )
        db.add(new_job)
        db.commit()

    # Pre-test metrics
    process = psutil.Process(os.getpid())
    start_cpu = psutil.cpu_percent(interval=1)
    start_mem = psutil.virtual_memory().used / (1024**3)
    start_time = time.time()

    logger.info(f"System Baseline - RAM: {start_mem:.2f}GB | CPU: {start_cpu}%")
    logger.info(f"Dispatching {count} tasks...")

    # Dispatch mock articles
    for i in range(count):
        article_data = {
            "url": f"https://example.com/stress-test-{job_id}-{i}",
            "title": f"Stress Test Article {i}",
            "published_at": datetime.now().isoformat()
        }
        # We use a real task but with a mock URL that will likely timeout/fail fast 
        # unless we mock the extraction too. 
        # For actual throughput of the QUEUE and DB, this is sufficient.
        scrape_article_node.delay(article_data, job_id, "Stress-Test", "India", "admin", scaling_mode=True)

    end_dispatch_time = time.time()
    logger.info(f"Dispatch complete in {end_dispatch_time - start_time:.2f}s")
    
    logger.info("Monitoring throughput (Target: 2.3 articles/sec)...")
    
    # Monitor for 60 seconds
    try:
        for _ in range(12): # 60 seconds total
            time.sleep(5)
            with get_db_sync() as db:
                from sqlalchemy import select
                job = db.execute(select(ScrapeJob).where(ScrapeJob.id == job_id)).scalar_one_or_none()
                done = job.total_scraped if job else 0
                
                curr_cpu = psutil.cpu_percent()
                curr_mem = psutil.virtual_memory().used / (1024**3)
                
                elapsed = time.time() - start_time
                rps = done / elapsed if elapsed > 0 else 0
                
                logger.info(f"Progress: {done}/{count} | Speed: {rps:.2f} art/sec | RAM: {curr_mem:.2f}GB | CPU: {curr_cpu}%")
                
                if done >= count:
                    logger.info("Stress test articles all processed!")
                    break
    except KeyboardInterrupt:
        logger.info("Monitoring interrupted.")

    final_time = time.time() - start_time
    logger.info(f"=== Stress Test Complete ===")
    logger.info(f"Total time: {final_time:.2f}s")
    logger.info(f"Avg Throughput: {count / final_time:.2f} articles/sec")

if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    run_stress_test(count)
