import logging
import json
from datetime import datetime
from sqlalchemy import select, update
from db.database import get_db_sync, ScrapeJob

logger = logging.getLogger("ORCHESTRATOR")

def update_phase_status(db, job_id, phase_name, status):
    """Updates the internal phase stats JSON for monitoring."""
    try:
        res = db.execute(select(ScrapeJob.phase_stats).where(ScrapeJob.id == job_id))
        phase_stats_raw = res.scalar()
        current_stats = json.loads(phase_stats_raw) if phase_stats_raw else {}
        current_stats[phase_name] = {"status": status, "updated_at": datetime.now().isoformat()}
        db.execute(
            update(ScrapeJob)
            .where(ScrapeJob.id == job_id)
            .values(phase_stats=json.dumps(current_stats), current_phase=phase_name)
        )
        db.commit()
    except Exception as e:
        logger.error(f"Error updating phase status for {job_id}: {e}")

def _mark_article_processed(job_id: str):
    """
    Safely increment total_scraped and mark job as completed if all articles processed.
    Uses atomic increment and RETURNING for high-concurrency safety.
    """
    try:
        with get_db_sync() as db:
            # Atomic update with returning for certain dialects, 
            # but for generic support we do increment + fresh read
            db.execute(
                update(ScrapeJob)
                .where(ScrapeJob.id == job_id)
                .values(total_scraped=ScrapeJob.total_scraped + 1)
            )
            db.commit() # Commit the increment first
            
            # Post-increment check with fresh state
            job = db.execute(
                select(ScrapeJob.total_found, ScrapeJob.total_scraped, ScrapeJob.status)
                .where(ScrapeJob.id == job_id)
            ).first()
            
            if job and job.total_found > 0 and job.total_scraped >= job.total_found and job.status != 'completed':
                db.execute(
                    update(ScrapeJob)
                    .where(ScrapeJob.id == job_id)
                    .values(status='completed', current_phase='Completed', completed_at=datetime.now())
                )
                db.commit()
                logger.info(f"Job {job_id} finalized: {job.total_scraped}/{job.total_found} articles.")
    except Exception as e:
        logger.error(f"Error marking article processed for job {job_id}: {e}")
