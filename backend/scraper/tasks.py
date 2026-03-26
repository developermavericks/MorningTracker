import logging
import json
import httpx
import trafilatura
from datetime import datetime
from celery_app import app as celery_app
from db.database import get_db_sync, Article, ScrapeJob
from scraper.orchestrator import _mark_article_processed
from scraper.browser import scrape_url
from sqlalchemy import select, update

logger = logging.getLogger(__name__)


# _mark_article_processed moved to orchestrator.py


# ─── Orchestrator Task ────────────────────────────────────────────────────────

@celery_app.task(name="scraper.tasks.run_scrape_task", bind=True)
def run_scrape_task(self, job_id, sector, region, date_from, date_to, search_mode, user_id):
    """
    Orchestrator: Discovers URLs and dispatches independent scraping nodes.
    Now fully synchronous for gevent compatibility.
    Celery tasks run server-side and persist through user logout.
    """
    logger.info(f"Starting Orchestrator for job {job_id}")
    # Late import to break circularity
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

@celery_app.task(name="scraper.tasks.scrape_article_node", bind=True, rate_limit="100/m", max_retries=2, default_retry_delay=5)
def scrape_article_node(self, article_data, job_id, sector, region, user_id, scaling_mode=False):
    """
    Task Node 1: Fetches HTML and extracts raw body. 
    Optimized for 2.3 articles/sec in scaling mode.
    """
    from scraper.engine import scrape_only, is_job_cancelled
    from scraper.google_news import resolve_google_news_url_sync
    from scraper.llm import get_redis_sync
    
    try:
        if is_job_cancelled(job_id):
            logger.info(f"Scrape task halted for job {job_id} [Reason: Job Cancelled/Global Stop]")
            _mark_article_processed(job_id)
            return None

        url = article_data.get("url") or article_data.get("link")
        if not url:
            _mark_article_processed(job_id)
            return None
            
        # Resolve Google News redirect if needed (scaling mode sitemaps usually have direct URLs)
        resolved_url = url
        if "news.google.com" in url:
            resolved_url = resolve_google_news_url_sync(url)
        
        if not resolved_url:
            _mark_article_processed(job_id)
            return None
        
        # --- FAST-TRACK SCRAPING (httpx + trafilatura) ---
        html = None
        timeout = 5 if scaling_mode else 15
        
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"}
            # Use connection pooling via httpx.Client
            with httpx.Client(timeout=timeout, follow_redirects=True, limits=httpx.Limits(max_connections=10)) as client:
                resp = client.get(resolved_url, headers=headers)
                if resp.status_code == 200:
                    text_content = trafilatura.extract(resp.text)
                    if text_content and len(text_content) > 400:
                        html = resp.text
        except Exception as e:
            logger.debug(f"Fast-track failed for {resolved_url}: {e}")

        # --- FALLBACK: SUBPROCESS BROWSER (Disabled in scaling mode) ---
        if not html and not scaling_mode:
            logger.info(f"Falling back to Playwright for {resolved_url}")
            html = scrape_url(resolved_url)
            
        if not html:
            logger.warning(f"Scrape failed for {resolved_url} (Job: {job_id})")
            _mark_article_processed(job_id)
            return None

        # Move processed data back to article_data for Engine
        article_data["resolved_url"] = resolved_url
        article_data["raw_html"] = html

        article_id = scrape_only(article_data, job_id, sector, region, user_id)
        if article_id:
            # Mark as processed in Redis for O(1) deduplication in future discovery
            redis = get_redis_sync()
            url_hash = hashlib.md5(resolved_url.encode()).hexdigest()
            redis.sadd("nexus:processed_urls", url_hash)
            
            logger.info(f"Scraped article {article_id}. Triggering enrichment...")
            enrich_article_node.delay(article_id)
        else:
            _mark_article_processed(job_id)

    except Exception as e:
        logger.error(f"Scrape node failed for {article_data.get('url')}: {e}")
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
                context_agency=article.agency,
                extra_metadata=article.extra_metadata
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
