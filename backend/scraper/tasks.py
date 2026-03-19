import logging
import json
import httpx
import trafilatura
from datetime import datetime
from celery_app import app as celery_app
from db.database import get_db_sync, Article, ScrapeJob
from scraper.browser import scrape_url
from sqlalchemy import select, update

logger = logging.getLogger(__name__)


def _mark_article_processed(job_id: str):
    """
    Safely increment total_scraped and mark job as completed if all articles processed.
    This MUST be called on EVERY code path, success or failure, so jobs always complete.
    """
    try:
        with get_db_sync() as db:
            db.execute(
                update(ScrapeJob)
                .where(ScrapeJob.id == job_id)
                .values(total_scraped=ScrapeJob.total_scraped + 1)
            )
            db.commit()

            job = db.execute(select(ScrapeJob).where(ScrapeJob.id == job_id)).scalar_one_or_none()
            if job and job.total_found > 0 and job.total_scraped >= job.total_found:
                db.execute(
                    update(ScrapeJob)
                    .where(ScrapeJob.id == job_id)
                    .values(status='completed', current_phase='Completed', completed_at=datetime.now())
                )
                db.commit()
                logger.info(f"Job {job_id} completed: {job.total_scraped}/{job.total_found}")
    except Exception as e:
        logger.error(f"Error marking article processed for job {job_id}: {e}")


# ─── Orchestrator Task ────────────────────────────────────────────────────────

@celery_app.task(name="scraper.tasks.run_scrape_task", bind=True)
def run_scrape_task(self, job_id, sector, region, date_from, date_to, search_mode, user_id):
    """
    Orchestrator: Discovers URLs and dispatches independent scraping nodes.
    Now fully synchronous for gevent compatibility.
    Celery tasks run server-side and persist through user logout.
    """
    logger.info(f"Starting Orchestrator for job {job_id}")
    from scraper.engine import run_scrape_job
    try:
        run_scrape_job(
            job_id=job_id,
            sector=sector,
            region=region,
            date_from=date_from,
            date_to=date_to,
            search_mode=search_mode,
            user_id=user_id
        )
        logger.info(f"Discovery phase for job {job_id} completed.")
    except Exception as e:
        logger.error(f"Orchestrator failed for job {job_id}: {e}")
        raise e

# ─── Scraper Node (I/O Intensive) ─────────────────────────────────────────────

@celery_app.task(name="scraper.tasks.scrape_article_node", bind=True, rate_limit="30/m", max_retries=3, default_retry_delay=10)
def scrape_article_node(self, article_data, job_id, sector, region, user_id):
    """
    Task Node 1: Fetches HTML and extracts raw body. 
    Synchronous for gevent compatibility.
    Runs server-side independently of any user session.
    """
    from scraper.engine import scrape_only, is_job_cancelled
    from scraper.google_news import resolve_google_news_url_sync
    try:
        if is_job_cancelled(job_id):
            logger.info(f"Scrape task halted for job {job_id} [Reason: Job Cancelled/Global Stop]")
            _mark_article_processed(job_id)
            return None

        # Resolve Google News redirect in sync (httpx)
        url = article_data.get("url") or article_data.get("link")
        if not url:
            logger.warning(f"Task received article without URL: {article_data}")
            _mark_article_processed(job_id)
            return None
            
        resolved_url = resolve_google_news_url_sync(url)
        if not resolved_url:
            logger.warning(f"Could not resolve URL: {url}")
            _mark_article_processed(job_id)
            return None
        
        # --- FAST-TRACK SCRAPING (httpx + trafilatura) ---
        html = None
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"}
            with httpx.Client(timeout=15, follow_redirects=True) as client:
                resp = client.get(resolved_url, headers=headers)
                if resp.status_code == 200:
                    text_content = trafilatura.extract(resp.text)
                    # If we got a decent amount of text, we can skip Playwright!
                    if text_content and len(text_content) > 400:
                        logger.info(f"Fast-track success for {resolved_url} ({len(text_content)} chars)")
                        html = resp.text
        except Exception as e:
            logger.debug(f"Fast-track failed for {resolved_url}: {e}")

        # --- FALLBACK: SUBPROCESS BROWSER (fully isolated from Gevent) ---
        if not html:
            logger.info(f"Falling back to Playwright for {resolved_url}")
            html = scrape_url(resolved_url)
            
        if not html:
            logger.warning(f"Scrape failed (both fast-track and browser) for {resolved_url}")
            # CRITICAL: Must still increment counter so job can complete!
            _mark_article_processed(job_id)
            return None

        # Move processed data back to article_data for Engine
        article_data["resolved_url"] = resolved_url
        article_data["raw_html"] = html

        article_id = scrape_only(article_data, job_id, sector, region, user_id)
        if article_id:
            logger.info(f"Scraped raw content for article {article_id}. Triggering enrichment...")
            enrich_article_node.delay(article_id)
    except Exception as e:
        logger.error(f"Scrape node failed for {article_data.get('url')}: {e}")
        # On final retry failure, still increment so job doesn't hang
        if self.request.retries >= self.max_retries:
            _mark_article_processed(job_id)
        raise self.retry(exc=e)

# ─── Enrichment Node (Compute Intensive) ──────────────────────────────────────

@celery_app.task(name="scraper.tasks.enrich_article_node", bind=True, max_retries=3)
def enrich_article_node(self, article_id):
    """
    Task Node 2: Performs AI analysis (Grok/Groq).
    Runs server-side, completely independent of user session.
    """
    from scraper.llm import perform_full_enrichment_sync
    from scraper.engine import is_job_cancelled
    
    with get_db_sync() as db:
        res = db.execute(select(Article).where(Article.id == article_id))
        article = res.scalar_one_or_none()
        if not article or not article.full_body: return
        
        if is_job_cancelled(article.scrape_job_id):
            logger.info(f"Enrichment cancelled for job {article.scrape_job_id}. Skipping article {article_id}")
            return

        try:
            enriched_data = perform_full_enrichment_sync(
                article.full_body, 
                article.title, 
                article.resolved_url or article.url, 
                article.sector,
                context_agency=article.agency
            )
            
            article.summary = enriched_data.get("summary")
            article.sentiment = enriched_data.get("sentiment")
            article.tags = enriched_data.get("tags")
            if enriched_data.get("agency"): article.agency = enriched_data.get("agency")
            if enriched_data.get("author"): article.author = enriched_data.get("author")
            
            db.commit()
            logger.info(f"Successfully enriched article {article_id}")
        except Exception as e:
            logger.error(f"AI Enrichment failed for article {article_id}: {e}")
            raise self.retry(exc=e, countdown=60)


# ─── Stale Job Watchdog (runs every 5 minutes via Celery Beat) ────────────────

@celery_app.task(name="scraper.tasks.complete_stale_jobs")
def complete_stale_jobs():
    """
    Watchdog: Scans for jobs stuck in 'running' state and marks complete if all articles are scraped.
    Ensures jobs finish even if some tasks crash silently.
    Runs every 5 minutes via Celery Beat schedule.
    """
    from datetime import datetime, timedelta
    try:
        with get_db_sync() as db:
            stale_cutoff = datetime.now() - timedelta(minutes=10)
            running_jobs = db.execute(
                select(ScrapeJob).where(
                    ScrapeJob.status == 'running',
                    ScrapeJob.started_at < stale_cutoff,
                    ScrapeJob.total_found > 0
                )
            ).scalars().all()

            for job in running_jobs:
                # Force-complete if total_scraped is near total_found (within 3 to handle edge cases)
                if job.total_scraped >= max(0, job.total_found - 3):
                    db.execute(
                        update(ScrapeJob).where(ScrapeJob.id == job.id).values(
                            status='completed',
                            current_phase='Completed',
                            total_scraped=job.total_found,  # Correct the counter
                            completed_at=datetime.now()
                        )
                    )
                    logger.info(f"Watchdog force-completed stale job {job.id} ({job.total_scraped}/{job.total_found})")
            
            db.commit()
    except Exception as e:
        logger.error(f"Stale job watchdog error: {e}")
