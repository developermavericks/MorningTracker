import asyncio
import logging
import json
from celery_app import app as celery_app
from sqlalchemy import select, update
from db.database import get_db, Article, ScrapeJob, AsyncSessionLocal

import sys

logger = logging.getLogger(__name__)

def handle_loop_exception(loop, context):
    exception = context.get("exception")
    # Suppress WinError 10054 noise on Windows (ConnectionResetError)
    if isinstance(exception, ConnectionResetError) or (exception and "[WinError 10054]" in str(exception)):
        return
    loop.default_exception_handler(context)

def setup_event_loop():
    """Ensure Proactor loop is used on Windows for Playwright."""
    if sys.platform == 'win32':
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception as e:
            logger.warning(f"Could not set Proactor policy: {e}")
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    # Silence Windows noise
    loop.set_exception_handler(handle_loop_exception)
    return loop

# ─── Orchestrator Task ────────────────────────────────────────────────────────

@celery_app.task(name="scraper.tasks.run_scrape_task", bind=True)
def run_scrape_task(self, job_id, sector, region, date_from, date_to, search_mode, user_id):
    """
    Orchestrator: Discovers URLs and dispatches independent scraping nodes.
    """
    logger.info(f"Starting Orchestrator for job {job_id}")
    
    from scraper.engine import run_scrape_job
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(
            run_scrape_job(
                job_id=job_id,
                sector=sector,
                region=region,
                date_from=date_from,
                date_to=date_to,
                search_mode=search_mode,
                user_id=user_id
            )
        )
        logger.info(f"Discovery phase for job {job_id} completed.")
    except Exception as e:
        logger.error(f"Orchestrator failed for job {job_id}: {e}")
        raise e
    finally:
        # C-7: Robust loop cleanup to allow background DB cleanups
        try:
            pending = asyncio.all_tasks(loop)
            if pending:
                loop.run_until_complete(asyncio.wait(pending, timeout=2.0))
        except: pass
        loop.close()

# ─── Scraper Node (I/O Intensive) ─────────────────────────────────────────────

@celery_app.task(name="scraper.tasks.scrape_article_node", bind=True, rate_limit="30/m")
def scrape_article_node(self, article_data, job_id, sector, region, user_id):
    """
    Task Node 1: Fetches HTML and extracts raw body. 
    NO AI calls here.
    """
    from scraper.engine import scrape_only
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
        
    try:
        article_id = loop.run_until_complete(
            scrape_only(article_data, job_id, sector, region, user_id)
        )
        if article_id:
            logger.info(f"Scraped raw content for article {article_id}. Triggering enrichment...")
            # Chain the enrichment task
            enrich_article_node.delay(article_id)
    except Exception as e:
        logger.error(f"Scrape node failed for {article_data.get('url')}: {e}")
    finally:
        try:
            pending = asyncio.all_tasks(loop)
            if pending:
                loop.run_until_complete(asyncio.wait(pending, timeout=2.0))
        except: pass
        loop.close()

# ─── Enrichment Node (Compute Intensive) ──────────────────────────────────────

@celery_app.task(name="scraper.tasks.enrich_article_node", bind=True, max_retries=3)
def enrich_article_node(self, article_id):
    """
    Task Node 2: Performs AI analysis (Ollama/Groq).
    If AI fails, only this node retries; raw content is already safe in DB.
    """
    from scraper.llm import perform_full_enrichment
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
        
    async def run_enrichment():
        async with AsyncSessionLocal() as db:
            # 1. Fetch raw article
            res = await db.execute(select(Article).where(Article.id == article_id))
            article = res.scalar_one_or_none()
            if not article or not article.full_body:
                return
            
            # 2. Run AI Logic
            try:
                enriched_data = await perform_full_enrichment(article.full_body, article.title, article.url, article.sector)
                
                # 3. Update Article
                article.summary = enriched_data.get("summary")
                article.sentiment = enriched_data.get("sentiment")
                article.tags = enriched_data.get("tags")
                if enriched_data.get("agency"):
                    article.agency = enriched_data.get("agency")
                if enriched_data.get("author"):
                    article.author = enriched_data.get("author")
                
                await db.commit()
                logger.info(f"Successfully enriched article {article_id}")
            except Exception as ai_e:
                logger.error(f"AI Enrichment failed for article {article_id}: {ai_e}")
                raise ai_e

    try:
        loop.run_until_complete(run_enrichment())
    except Exception as e:
        # Retry logic for transient AI failures (e.g., rate limits)
        raise self.retry(exc=e, countdown=60)
    finally:
        try:
            pending = asyncio.all_tasks(loop)
            if pending:
                loop.run_until_complete(asyncio.wait(pending, timeout=2.0))
        except: pass
        loop.close()
