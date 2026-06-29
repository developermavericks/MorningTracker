import logging
import json
import os
import httpx
import trafilatura
import random
from datetime import datetime
from celery_app import app as celery_app
from db.database import get_db_sync, Article, ScrapeJob, IrrelevantArticle, JobFunnelLog, Client
from scraper.browser import scrape_url
from sqlalchemy import select, update, insert, delete
from scraper.engine import normalize_url
from scraper.llm import get_redis_sync
from scraper.search_utils import verify_boolean_relevance

logger = logging.getLogger(__name__)

PLAYWRIGHT_ONLY_DOMAINS = {"axios.com", "ndtv.com"}

# Rotate across several recent Chrome UA strings to avoid fingerprinting.
_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.6533.120 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.6533.120 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.6478.229 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.6533.120 Safari/537.36",
]

def _pick_ua() -> str:
    return random.choice(_UA_POOL)

def should_use_playwright(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return any(domain == d or domain.endswith("." + d) for d in PLAYWRIGHT_ONLY_DOMAINS)
    except Exception:
        return False

KNOWN_PAYWALLED_DOMAINS = {
    "the-ken.com", "livemint.com", "economictimes.indiatimes.com",
    "business-standard.com", "financialexpress.com",
    "wsj.com", "ft.com",
    "reuters.com", "bloomberg.com", "thehindu.com", "indianexpress.com",
    "moneycontrol.com", "timesofindia.indiatimes.com", "hindustantimes.com",
}

PAYWALL_HTML_INDICATORS = [
    "paywall", "premium-content", "subscription-wall", "subscribe-gate",
    "metered-content", "locked-content", "premium-article",
    "subscribe to continue reading", "exclusive to subscribers",
    "premium article", "this article is for subscribers",
    "you have reached your free article limit",
    "sign up to read this article", "become a member to read",
]

def detect_paywall(url: str, html_content: str, body_text: str) -> bool:
    """
    Detects if an article is behind a paywall using three methods:
    1. Known paywalled domain matching
    2. HTML content heuristic scanning for paywall indicators
    3. Body length anomaly (short body text but large HTML)
    """
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        # 1. Known domain check
        if any(domain == d or domain.endswith("." + d) for d in KNOWN_PAYWALLED_DOMAINS):
            return True
    except Exception:
        pass

    # 2. HTML heuristic check
    if html_content:
        html_lower = html_content[:20000].lower()  # Only scan first 20KB for performance
        for indicator in PAYWALL_HTML_INDICATORS:
            if indicator in html_lower:
                return True

    # 3. Body length anomaly: short extracted text from a large HTML page
    if html_content and body_text:
        if len(body_text) < 200 and len(html_content) > 5000:
            return True

    return False

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

def _increment_funnel_metric(job_id: str, field_name: str, amount: int = 1):
    if not job_id:
        return
    try:
        with get_db_sync() as db:
            log_entry = db.execute(select(JobFunnelLog).where(JobFunnelLog.job_id == job_id)).scalar_one_or_none()
            if not log_entry:
                log_entry = JobFunnelLog(job_id=job_id)
                db.add(log_entry)
                db.commit()
                db.refresh(log_entry)
            
            val = getattr(log_entry, field_name, 0) or 0
            setattr(log_entry, field_name, val + amount)
            db.commit()
    except Exception as e:
        logger.error(f"Error logging funnel metric for job {job_id}: {e}")


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

@celery_app.task(
    name="scraper.tasks.scrape_article_node",
    bind=True,
    rate_limit="100/m",
    max_retries=10,
    retry_backoff=15,    # Exponential backoff starting at 15s
    retry_jitter=True    # Jitter backoff offsets
)
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
        
        # ─── URL NORMALIZATION ───
        normalized_url = normalize_url(resolved_url)
        
        # ─── DB CACHE CHECK ───
        with get_db_sync() as db:
            # Check existing
            existing_article = db.execute(
                select(Article.id)
                .where(Article.url == normalized_url)
                .where(Article.user_id == user_id)
            ).first()
            if existing_article:
                logger.info(f"Celery DB Cache HIT (already exists): {normalized_url}. Skipping.")
                _mark_article_processed(job_id)
                _increment_funnel_metric(job_id, "cache_skipped")
                return None
                
            # Check irrelevant
            cached_irrelevant = db.execute(
                select(IrrelevantArticle)
                .where(IrrelevantArticle.url == normalized_url)
            ).scalar_one_or_none()
            if cached_irrelevant:
                age = datetime.now() - cached_irrelevant.last_seen_at
                if age.days < 30:
                    logger.info(f"Celery Irrelevant Cache HIT: {normalized_url}. Skipping.")
                    _mark_article_processed(job_id)
                    _increment_funnel_metric(job_id, "cache_skipped")
                    return None
                else:
                    db.delete(cached_irrelevant)
                    db.commit()

        # ─── LOCKING ───
        lock_key = f"lock:scrape:{normalized_url}"
        r = get_redis_sync()
        if not r.set(lock_key, job_id, nx=True, ex=600):
            logger.info(f"Task overlap detected for {normalized_url}. Skipping redundant node.")
            _mark_article_processed(job_id)
            return None

        # ─── DOMAIN RATE LIMITING (Throttling) ───
        from urllib.parse import urlparse
        domain = urlparse(resolved_url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
            
        domain_lock_key = f"lock:domain:{domain}"
        if not r.set(domain_lock_key, job_id, nx=True, ex=2):
            logger.info(f"Domain rate limit triggered for {domain}. Rescheduling task.")
            # Retry after a short randomized jitter countdown (3-7s)
            raise self.retry(countdown=random.randint(3, 7))

        # ─── FAST-REJECT PRE-FILTER ───
        keywords = []
        with get_db_sync() as db:
            from db.database import WatchedBrand
            brand_obj = db.execute(
                select(WatchedBrand)
                .where(WatchedBrand.name == sector)
                .where(WatchedBrand.user_id == user_id)
            ).first()
            if brand_obj:
                brand_obj = brand_obj[0]
                if brand_obj.keywords:
                    keywords = [k.strip() for k in brand_obj.keywords.split(",") if k.strip()]
        
        if not keywords:
            from scraper.config import SECTOR_KEYWORDS
            keywords.extend(SECTOR_KEYWORDS.get(sector.lower(), []))
            
        title = article_data.get("title", "")
        description = article_data.get("description", "")
        text_to_check = f"{title} {description}"
        
        # Check publication category first to bypass fast-reject for Category A
        from scraper.search_utils import match_publication_category
        url_to_check = article_data.get("url") or article_data.get("link")
        agency_to_check = article_data.get("agency") or "News"
        pub_category = match_publication_category(agency_to_check, url_to_check)
        is_cat_a = (pub_category == "A")

        # Fast-reject keyword pre-filter is temporarily disabled for maximum recall
        is_pre_filtered_relevant = True
        # Original keyword filter (commented out to allow switching back):
        # if is_cat_a:
        #     is_pre_filtered_relevant = True
        # elif keywords:
        #     is_pre_filtered_relevant = verify_boolean_relevance(text_to_check, keywords)
        #     if not is_pre_filtered_relevant and sector.lower() in text_to_check.lower():
        #         is_pre_filtered_relevant = True
        #         
        # if not is_pre_filtered_relevant:
        #     logger.info(f"Fast-reject (Celery): article '{title}' failed keyword pre-filter. Skipping.")
        #     with get_db_sync() as db:
        #         db.merge(IrrelevantArticle(url=normalized_url, last_seen_at=datetime.now()))
        #         db.commit()
        #     _mark_article_processed(job_id)
        #     _increment_funnel_metric(job_id, "pre_filter_dropped")
        #     return None

        # --- FAST-TRACK SCRAPING (httpx + trafilatura) ---
        html = None
        if not should_use_playwright(resolved_url):
            try:
                headers = {
                    "User-Agent": _pick_ua(),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://news.google.com/",
                    "Cache-Control": "no-cache",
                }
                with httpx.Client(timeout=httpx.Timeout(15.0, connect=8.0), follow_redirects=True) as client:
                    resp = client.get(resolved_url, headers=headers)
                    if resp.status_code == 429:
                        logger.info(f"Rate limited (429) by {resolved_url}, skipping to Playwright")
                    elif resp.status_code == 200:
                        text_content = trafilatura.extract(resp.text)
                        if text_content and len(text_content) > 400:
                            logger.info(f"Fast-track success for {resolved_url} ({len(text_content)} chars)")
                            html = resp.text
                        else:
                            logger.debug(f"Fast-track got HTML but <400 chars text ({len(text_content or '')} chars), falling to Playwright")
            except Exception as e:
                logger.debug(f"Fast-track failed for {resolved_url}: {e}")
        else:
            logger.info(f"Skipping fast-track HTTP client for known hostile domain: {resolved_url}")

        # --- FALLBACK: SUBPROCESS BROWSER (fully isolated from Gevent) ---
        if not html:
            logger.info(f"Falling back to Playwright for {resolved_url}")
            html = scrape_url(resolved_url)
            
        if not html:
            logger.warning(f"Scrape failed (both fast-track and browser) for {resolved_url}")
            _mark_article_processed(job_id)
            return None
            
        _increment_funnel_metric(job_id, "scraped_count")

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
    from scraper.llm import perform_full_enrichment_sync, check_relevance_with_groq
    from scraper.engine import is_job_cancelled
    
    with get_db_sync() as db:
        res = db.execute(select(Article).where(Article.id == article_id))
        article = res.scalar_one_or_none()
        if not article or not article.full_body: return
        
        if is_job_cancelled(article.scrape_job_id):
            logger.info(f"Enrichment cancelled for job {article.scrape_job_id}. Skipping article {article_id}")
            return

        # ─── RELEVANCE CHECK (120B Model) ───
        try:
            keywords = []
            from db.database import WatchedBrand
            brand_obj = db.execute(
                select(WatchedBrand)
                .where(WatchedBrand.name == article.sector)
                .where(WatchedBrand.user_id == article.user_id)
            ).first()
            if brand_obj:
                brand_obj = brand_obj[0]
                if brand_obj.keywords:
                    keywords = [k.strip() for k in brand_obj.keywords.split(",") if k.strip()]
            
            if not keywords:
                from scraper.config import SECTOR_KEYWORDS
                keywords.extend(SECTOR_KEYWORDS.get(article.sector.lower(), []))
            
            # Retrieve client context guidelines if applicable
            client_context = ""
            client_name = article.sector
            if " - " in client_name:
                client_name = client_name.split(" - ")[0]
            client_obj = db.execute(
                select(Client).where(Client.name == client_name)
            ).scalars().first()
            if client_obj:
                client_context = client_obj.context or ""
            
            # --- Similarity Pre-Filter ---
            from scraper.similarity import evaluate_similarity_pre_filter, SIM_DROP_THRESHOLD
            sim_score = evaluate_similarity_pre_filter(
                article.title, article.full_body, keywords, client_context
            )
            # Cosine similarity pre-filter drop is temporarily disabled for maximum recall
            logger.info(f"Cosine similarity pre-filter drop bypassed for article {article_id}: '{article.title}' (score: {sim_score:.4f} < {SIM_DROP_THRESHOLD}).")

            # --- LLM Relevance Check ---
            is_semantic_relevant, verdict, reason, score = check_relevance_with_groq(
                article.title, article.full_body, keywords, client_name, client_context=client_context
            )
        except Exception as rel_err:
            logger.error(f"Relevance check exception in Celery task: {rel_err}")
            is_semantic_relevant = True # Fallback
            verdict = "uncertain"
            reason = f"Exception: {rel_err}"
            score = 0.5
            
        if not is_semantic_relevant:
            logger.info(f"Article {article_id} rejected by relevance check (verdict: {verdict}, score: {score}). Deleting and caching.")
            from db.database import IrrelevantArticle
            db.merge(IrrelevantArticle(
                url=article.url,
                title=article.title,
                description=article.summary or (article.full_body[:200] if article.full_body else ""),
                rejection_reason=reason,
                relevance_score=score,
                last_seen_at=datetime.now()
            ))
            db.delete(article)
            db.commit()
            _increment_funnel_metric(article.scrape_job_id, "relevance_no")
            return
            
        _increment_funnel_metric(article.scrape_job_id, "relevance_yes")

        # ─── SUMMARIZATION & ENRICHMENT ───
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
            _increment_funnel_metric(article.scrape_job_id, "summarized_count")
            logger.info(f"Successfully enriched article {article_id}")
        except Exception as e:
            logger.error(f"AI Enrichment failed for article {article_id}: {e}")
            raise self.retry(exc=e, countdown=15)


# ─── Stale Job Watchdog (runs every 5 minutes via Celery Beat) ────────────────

@celery_app.task(name="scraper.tasks.complete_stale_jobs")
def complete_stale_jobs():
    """
    Watchdog: Scans for jobs stuck in 'running' state and marks complete if all articles are scraped.
    Ensures jobs finish even if some tasks crash silently.
    Runs every 5 minutes via Celery Beat schedule.
    """
    from datetime import datetime, timedelta
    from db.database import ClientRunLog
    
    # Redis Lock to prevent duplicate runs from concurrent schedulers
    try:
        r = get_redis_sync()
        current_minute = datetime.now().minute
        minute_block = current_minute - (current_minute % 5)
        lock_key = f"lock:scheduler:stale:{datetime.now().strftime('%Y-%m-%d-%H')}-{minute_block}"
        if not r.set(lock_key, "1", nx=True, ex=240):
            logger.info("Stale jobs cleanup already processed by another instance. Skipping.")
            return
    except Exception as lock_err:
        logger.warning(f"Failed to acquire Redis stale-jobs lock: {lock_err}")
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
            
            # Clean up stuck client run logs (older than 120 minutes)
            client_stale_cutoff = datetime.now() - timedelta(minutes=120)
            stale_client_logs = db.execute(
                select(ClientRunLog).where(
                    ClientRunLog.status == 'running',
                    ClientRunLog.started_at < client_stale_cutoff
                )
            ).scalars().all()
            
            for log_entry in stale_client_logs:
                db.execute(
                    update(ClientRunLog).where(ClientRunLog.id == log_entry.id).values(
                        status='failed',
                        error_message='Task timed out or was interrupted (Watchdog recovery)',
                        completed_at=datetime.now()
                    )
                )
                logger.info(f"Watchdog force-failed stale client run log {log_entry.id}")
            
            db.commit()
    except Exception as e:
        logger.error(f"Stale job watchdog error: {e}")


@celery_app.task(name="scraper.tasks.run_client_report_task")
def run_client_report_task(client_id: int):
    """
    Main background task to generate daily monitoring briefing reports for a client.
    """
    from db.database import get_db_sync, Client, ClientSection, ClientKeyword, ClientRecipient, ClientRunLog
    from scraper.engine import discover_articles
    from scraper.google_news import resolve_google_news_url_sync
    from scraper.report_generator import generate_docx_report
    from utils.google_docs import upload_docx_to_google_doc
    from utils.email import send_report_email, send_error_alert_email
    from scraper.llm import perform_full_enrichment_sync
    from datetime import date, datetime, timedelta
    import pytz
    import traceback
    
    client_name = f"Client ID {client_id}"
    logger.info(f"Starting client report task for client_id {client_id}")
    
    # Create a running log entry
    run_log_id = None
    with get_db_sync() as db:
        client = db.execute(select(Client).where(Client.id == client_id)).scalar_one_or_none()
        if not client:
            logger.error(f"Client with ID {client_id} not found.")
            return False
            
        run_log = ClientRunLog(
            client_id=client_id,
            status="running",
            started_at=datetime.utcnow()
        )
        db.add(run_log)
        db.commit()
        db.refresh(run_log)
        run_log_id = run_log.id
        client_name = client.name
        template_path = client.template_path
        client_context = client.context
        client_timezone = client.timezone or "Asia/Kolkata"
        
    try:
        def _update_progress(msg: str):
            try:
                timestamp = datetime.now().strftime("%H:%M:%S")
                log_line = f"[{timestamp}] {msg}"
                with get_db_sync() as db:
                    run_log = db.execute(select(ClientRunLog).where(ClientRunLog.id == run_log_id)).scalar_one_or_none()
                    if run_log:
                        current_log = run_log.progress_message or ""
                        updated_log = f"{current_log}\n{log_line}" if current_log else log_line
                        db.execute(
                            update(ClientRunLog)
                            .where(ClientRunLog.id == run_log_id)
                            .values(progress_message=updated_log)
                        )
                        db.commit()
            except Exception as dberr:
                logger.error(f"Failed to update progress log in DB: {dberr}")

        _update_progress("Initializing client report profile...")
        
        # Load sections and keywords
        sections_data = {}
        all_emails = []
        
        with get_db_sync() as db:
            sections = db.execute(select(ClientSection).where(ClientSection.client_id == client_id)).scalars().all()
            recipients = db.execute(select(ClientRecipient).where(ClientRecipient.client_id == client_id)).scalars().all()
            all_emails = [r.email for r in recipients]
            
            for section in sections:
                kwd_objs = db.execute(select(ClientKeyword).where(ClientKeyword.section_id == section.id)).scalars().all()
                sections_data[section.name] = [k.keyword for k in kwd_objs]
                
        if not sections_data:
            raise ValueError("No sections or keywords configured for this client.")
            
        # Discover, scrape, verify and enrich articles for each section
        report_data_filtered = {} # {section_name: [list of article dicts]}
        report_data_master = {} # {section_name: [list of article dicts]}
        
        # Determine the search window based on the day of the week in client's timezone
        client_tz = pytz.timezone(client_timezone)
        run_date = datetime.now(client_tz).date()
        
        search_dates = [run_date]
        if run_date.weekday() == 0:  # 0 is Monday
            # On Monday, consolidate Friday, Saturday, Sunday, and Monday
            search_dates.extend([
                run_date - timedelta(days=1),  # Sunday
                run_date - timedelta(days=2),  # Saturday
                run_date - timedelta(days=3)   # Friday
            ])
        else:
            # On other weekdays, search today and yesterday
            search_dates.append(run_date - timedelta(days=1))
            
        # ── Phase 1: Discover articles for ALL sections in parallel ──────────────
        from scraper.engine import discover_direct_feeds
        from concurrent.futures import ThreadPoolExecutor as _TPE, as_completed as _ac

        def _discover_section(section_name_kws):
            sec_name, kws = section_name_kws
            if not kws:
                return sec_name, []
            job_id_disc = f"client_{client_id}_sec_{sec_name}"
            try:
                # Init funnel log
                try:
                    with get_db_sync() as db:
                        db.execute(delete(JobFunnelLog).where(JobFunnelLog.job_id == job_id_disc))
                        db.execute(insert(JobFunnelLog).values(job_id=job_id_disc, rss_discovered=0))
                        db.commit()
                except Exception as e:
                    logger.error(f"Failed to initialize funnel log for section '{sec_name}': {e}")

                discovered = []
                seen_urls = set()
                for target_date in search_dates:
                    date_job = f"client_{client_id}_sec_{sec_name}_{target_date.strftime('%Y%m%d')}"
                    for art in discover_articles(keywords=kws, day=target_date, geo="IN", region_name="india",
                                                 job_id=date_job, sector=f"{client_name} - {sec_name}"):
                        if art["url"] not in seen_urls:
                            discovered.append(art)
                            seen_urls.add(art["url"])
                    for art in discover_direct_feeds(keywords=kws, day=target_date, job_id=date_job,
                                                     sector=f"{client_name} - {sec_name}"):
                        if art["url"] not in seen_urls:
                            discovered.append(art)
                            seen_urls.add(art["url"])

                try:
                    with get_db_sync() as db:
                        db.execute(update(JobFunnelLog).where(JobFunnelLog.job_id == job_id_disc)
                                   .values(rss_discovered=len(discovered)))
                        db.commit()
                except Exception:
                    pass
                return sec_name, discovered
            except Exception as disc_err:
                # A discovery failure for one section must not crash the whole report.
                logger.error(f"Discovery failed for section '{sec_name}': {disc_err}", exc_info=True)
                return sec_name, []

        # Emit per-section discovery messages upfront (matches old log format)
        section_discoveries: dict = {}
        active_sections = {sn: kw for sn, kw in sections_data.items() if kw}
        for sec_name in active_sections:
            _update_progress(f"Discovering articles for section '{sec_name}'...")
            logger.info(f"Discovering articles for section '{sec_name}' with keywords: {active_sections[sec_name]}")

        if active_sections:
            disc_workers = min(len(active_sections), 4)
            with _TPE(max_workers=disc_workers) as disc_exe:
                disc_futures = {disc_exe.submit(_discover_section, item): item[0] for item in active_sections.items()}
                for fut in _ac(disc_futures):
                    sec_name, disc = fut.result()
                    section_discoveries[sec_name] = disc
                    logger.info(f"Discovery done for '{sec_name}': {len(disc)} articles found.")

        # ── Phase 2: Process articles per section (ALL sections in parallel) ──
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _process_section(section_name, keywords):
            if not keywords:
                return section_name, [], []

            discovered = section_discoveries.get(section_name, [])

            # Deduplicate by url
            unique_discovered = []
            seen_urls = set()
            for art in discovered:
                if art["url"] not in seen_urls:
                    unique_discovered.append(art)
                    seen_urls.add(art["url"])

            filtered_section_articles = []
            master_section_articles = []

            # Resolve and scrape each article concurrently
            
            def _process_single_article(art_idx_tuple):
                art, idx = art_idx_tuple
                raw_url = art["url"]
                title = art["title"]
                desc = art.get("description") or ""
                # Strip HTML tags from RSS description (Google News RSS contains raw HTML markup)
                if desc and "<" in desc:
                    import re
                    desc = re.sub(r'<[^>]+>', '', desc).strip()
                    desc = re.sub(r'&nbsp;', ' ', desc)
                    desc = re.sub(r'\s{2,}', ' ', desc).strip()
                agency = art.get("agency") or "News"
                
                job_id = f"client_{client_id}_sec_{section_name}"
                
                try:
                    # 1. Normalize raw URL for early checks
                    normalized_raw_url = normalize_url(raw_url)
                    
                    # 2. Check early cache for existing/irrelevant using raw URL
                    with get_db_sync() as db:
                        from db.database import IrrelevantArticle
                        # Check existing
                        existing_article = db.execute(
                            select(Article)
                            .where(Article.url == normalized_raw_url)
                        ).scalars().first()
                        if existing_article and existing_article.full_body and existing_article.summary:
                            logger.info(f"Early DB Cache HIT for {normalized_raw_url}")
                            _increment_funnel_metric(job_id, "cache_skipped")
                            
                            from scraper.search_utils import match_publication_category
                            cached_meta = existing_article.extra_metadata or {}
                            pub_category = cached_meta.get("publication_category")
                            if not pub_category:
                                pub_category = match_publication_category(existing_article.agency or agency, existing_article.resolved_url or existing_article.url)
                            
                            return {
                                "art_data": {
                                    "title": existing_article.title,
                                    "url": existing_article.resolved_url or existing_article.url,
                                    "agency": existing_article.agency or agency,
                                    "summary": existing_article.summary,
                                    "publication_category": pub_category
                                },
                                "is_relevant_kw": True,
                                "is_semantic_relevant": True
                            }
                        
                        # Check irrelevant
                        cached_ir = db.execute(
                            select(IrrelevantArticle)
                            .where(IrrelevantArticle.url == normalized_raw_url)
                        ).scalar_one_or_none()
                        if cached_ir:
                            age = datetime.now() - cached_ir.last_seen_at
                            if age.days < 30:
                                logger.info(f"Early Irrelevant Cache HIT for {normalized_raw_url}")
                                _increment_funnel_metric(job_id, "cache_skipped")
                                from scraper.search_utils import match_publication_category
                                return {
                                    "art_data": {
                                        "title": cached_ir.title or title,
                                        "url": raw_url,
                                        "agency": agency,
                                        "summary": cached_ir.description or desc or "Irrelevant article cached.",
                                        "publication_category": match_publication_category(agency, raw_url)
                                    },
                                    "is_relevant_kw": True,
                                    "is_semantic_relevant": False
                                }
                            else:
                                db.delete(cached_ir)
                                db.commit()
                                
                    # 3. Triage pre-filter (fast reject)
                    text_to_check = f"{title} {desc}"
                    
                    # Check publication category first to bypass fast-reject for Category A
                    from scraper.search_utils import match_publication_category
                    pub_category = match_publication_category(agency, raw_url)
                    is_cat_a = (pub_category == "A")

                    # Fast-reject keyword pre-filter is temporarily disabled for maximum recall
                    is_relevant_kw = True
                    # Original keyword filter (commented out to allow switching back):
                    # if is_cat_a:
                    #     is_relevant_kw = True
                    # else:
                    #     is_relevant_kw = verify_boolean_relevance(text_to_check, keywords)
                    #     if not is_relevant_kw and section_name.lower() in text_to_check.lower():
                    #         is_relevant_kw = True
                    #     
                    # if not is_relevant_kw:
                    #     logger.info(f"Fast-reject: article '{title}' failed pre-filter.")
                    #     # Cache as irrelevant in DB
                    #     with get_db_sync() as db:
                    #         db.merge(IrrelevantArticle(url=normalized_raw_url, last_seen_at=datetime.now()))
                    #         db.commit()
                    #     _increment_funnel_metric(job_id, "pre_filter_dropped")
                    #     return None
                        
                    # 4. Resolve URL
                    logger.info(f"Resolving Google News URL: {raw_url}")
                    resolved_url = resolve_google_news_url_sync(raw_url)
                    if not resolved_url:
                        # Resolution failed — URL is still on Google's domain (redirect page).
                        # Scraping it would return a redirect notice page and falsely trigger
                        # paywall detection. Skip the article entirely.
                        logger.warning(f"Skipping unresolvable Google News URL: {raw_url}")
                        _increment_funnel_metric(job_id, "resolution_failed")
                        return None
                    normalized_url = normalize_url(resolved_url)
                    
                    # 5. Check cache for canonical URL
                    with get_db_sync() as db:
                        # Check existing
                        existing_article = db.execute(
                            select(Article)
                            .where(Article.url == normalized_url)
                        ).scalars().first()
                        if existing_article and existing_article.full_body and existing_article.summary:
                            logger.info(f"Canonical DB Cache HIT for {normalized_url}")
                            _increment_funnel_metric(job_id, "cache_skipped")
                            
                            from scraper.search_utils import match_publication_category
                            cached_meta = existing_article.extra_metadata or {}
                            pub_category = cached_meta.get("publication_category")
                            if not pub_category:
                                pub_category = match_publication_category(existing_article.agency or agency, existing_article.resolved_url or existing_article.url)
                                
                            return {
                                "art_data": {
                                    "title": existing_article.title,
                                    "url": existing_article.resolved_url or existing_article.url,
                                    "agency": existing_article.agency or agency,
                                    "summary": existing_article.summary,
                                    "publication_category": pub_category,
                                    "is_paywalled": False
                                },
                                "is_relevant_kw": True,
                                "is_semantic_relevant": True
                            }
                            
                        # Check irrelevant
                        cached_ir = db.execute(
                            select(IrrelevantArticle)
                            .where(IrrelevantArticle.url == normalized_url)
                        ).scalar_one_or_none()
                        if cached_ir:
                            age = datetime.now() - cached_ir.last_seen_at
                            if age.days < 30:
                                logger.info(f"Canonical Irrelevant Cache HIT for {normalized_url}")
                                _increment_funnel_metric(job_id, "cache_skipped")
                                from scraper.search_utils import match_publication_category
                                return {
                                    "art_data": {
                                        "title": cached_ir.title or title,
                                        "url": resolved_url,
                                        "agency": agency,
                                        "summary": cached_ir.description or desc or "Irrelevant article cached.",
                                        "publication_category": match_publication_category(agency, resolved_url),
                                        "is_paywalled": False
                                    },
                                    "is_relevant_kw": True,
                                    "is_semantic_relevant": False
                                }
                            else:
                                db.delete(cached_ir)
                                db.commit()

                    # 6. Scrape HTML content
                    logger.info(f"Scraping content from resolved URL: {resolved_url}")
                    html_content = ""
                    _fast_body_chars = 0
                    if not should_use_playwright(resolved_url):
                        try:
                            headers = {
                                "User-Agent": _pick_ua(),
                                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                                "Accept-Language": "en-US,en;q=0.9",
                                "Referer": "https://news.google.com/",
                                "Cache-Control": "no-cache",
                            }
                            with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(12.0, connect=8.0)) as client_http:
                                resp = client_http.get(resolved_url, headers=headers)
                                if resp.status_code == 429:
                                    logger.info(f"Rate limited (429) by {resolved_url}, falling back to Playwright")
                                elif resp.status_code == 200:
                                    html_content = resp.text
                                    _fast_body_chars = len(trafilatura.extract(html_content) or "")
                        except Exception as e:
                            logger.warning(f"Fast HTTP scrape failed for {resolved_url}: {e}")
                    else:
                        logger.info(f"Skipping fast HTTP scrape for known hostile domain: {resolved_url}")

                    # Trigger Playwright if httpx failed entirely, or if it returned HTML
                    # but trafilatura could only extract <300 chars — indicates a JS-rendered
                    # or subscription-wall page that needs a real browser to get content.
                    if not html_content or _fast_body_chars < 300:
                        try:
                            logger.info(f"Falling back to Playwright for {resolved_url} (fast-track body: {_fast_body_chars} chars)")
                            pw_html = scrape_url(resolved_url)
                            if pw_html:
                                html_content = pw_html  # Use Playwright result; better than wall HTML
                        except Exception as e:
                            logger.error(f"Browser scrape failed for {resolved_url}: {e}")
                            
                    if not html_content:
                        logger.warning(f"Could not fetch HTML content for {resolved_url}.")
                        from scraper.search_utils import match_publication_category
                        pub_cat = match_publication_category(agency, resolved_url)
                        is_pw = detect_paywall(resolved_url, "", "")
                        
                        # Category A zero-failure fallback
                        if pub_cat == "A":
                            logger.info(f"Scraper failed for Category A url {resolved_url}. Applying zero-failure fallback.")
                            is_relevant_fallback = True
                            # Use desc if available; fall back to title so LLM always has some signal
                            fallback_content = desc.strip() if (desc and len(desc.strip()) > 10) else title
                            fallback_summary = fallback_content if len(fallback_content) > 20 else f"[Paywalled/blocked] {title}"
                            try:
                                from scraper.llm import check_relevance_with_groq
                                is_relevant_fallback, _, _, _ = check_relevance_with_groq(
                                    title, fallback_content, keywords, client_name, client_context=client_context
                                )
                            except Exception as fallback_err:
                                logger.error(f"Fallback LLM relevance check failed for Category A: {fallback_err}")
                                is_relevant_fallback = True
                            if is_relevant_fallback:
                                return {
                                    "art_data": {
                                        "title": title,
                                        "url": resolved_url,
                                        "agency": agency,
                                        "summary": fallback_summary,
                                        "publication_category": pub_cat,
                                        "is_paywalled": True
                                    },
                                    "is_relevant_kw": True,
                                    "is_semantic_relevant": True
                                }

                        if is_pw and desc:
                            # Paywalled: run LLM relevance on headline + RSS description
                            logger.info(f"Paywall detected for {resolved_url}. Running LLM relevance on title+description.")
                            try:
                                from scraper.llm import check_relevance_with_groq
                                pw_relevant, _, _, _ = check_relevance_with_groq(
                                    title, desc, keywords, client_name, client_context=client_context
                                )
                            except Exception as pw_err:
                                logger.error(f"Paywall LLM relevance check failed: {pw_err}")
                                pw_relevant = False
                            
                            if pw_relevant:
                                logger.info(f"Paywalled article '{title}' deemed RELEVANT by LLM.")
                                return {
                                    "art_data": {
                                        "title": title,
                                        "url": resolved_url,
                                        "agency": agency,
                                        "summary": desc,
                                        "publication_category": pub_cat,
                                        "is_paywalled": True
                                    },
                                    "is_relevant_kw": True,
                                    "is_semantic_relevant": True
                                }
                        
                        return {
                            "art_data": {
                                "title": title,
                                "url": resolved_url,
                                "agency": agency,
                                "summary": desc or "Could not fetch HTML content.",
                                "publication_category": pub_cat,
                                "is_paywalled": is_pw
                            },
                            "is_relevant_kw": True,
                            "is_semantic_relevant": False
                        }
                        
                    _increment_funnel_metric(job_id, "scraped_count")
                        
                    # 7. Extract body text
                    from scraper.parser import extract_body
                    body_text = extract_body(html_content)
                        
                    if not body_text or len(body_text) < 100:
                        logger.warning(f"No meaningful text extracted for {resolved_url}.")
                        from scraper.search_utils import match_publication_category
                        pub_cat = match_publication_category(agency, resolved_url)
                        is_pw = detect_paywall(resolved_url, html_content, body_text or "")
                        
                        # Category A zero-failure fallback
                        if pub_cat == "A":
                            logger.info(f"Extraction failed for Category A url {resolved_url}. Applying zero-failure fallback.")
                            is_relevant_fallback = True
                            # Combine partial body + desc + title so LLM always has signal
                            fallback_content = " ".join(filter(None, [body_text or "", desc or ""])).strip() or title
                            fallback_summary = fallback_content if len(fallback_content) > 20 else f"[Paywalled/blocked] {title}"
                            try:
                                from scraper.llm import check_relevance_with_groq
                                is_relevant_fallback, _, _, _ = check_relevance_with_groq(
                                    title, fallback_content, keywords, client_name, client_context=client_context
                                )
                            except Exception as fallback_err:
                                logger.error(f"Fallback LLM relevance check failed for Category A: {fallback_err}")
                                is_relevant_fallback = True
                            if is_relevant_fallback:
                                return {
                                    "art_data": {
                                        "title": title,
                                        "url": resolved_url,
                                        "agency": agency,
                                        "summary": fallback_summary,
                                        "publication_category": pub_cat,
                                        "is_paywalled": True
                                    },
                                    "is_relevant_kw": True,
                                    "is_semantic_relevant": True
                                }

                        if is_pw:
                            # Paywalled: run LLM relevance on headline + available text + RSS description
                            fallback_text = " ".join(filter(None, [body_text or "", desc or ""])).strip() or title
                            if fallback_text:
                                logger.info(f"Paywall detected for {resolved_url}. Running LLM relevance on partial content.")
                                try:
                                    from scraper.llm import check_relevance_with_groq
                                    pw_relevant, _, _, _ = check_relevance_with_groq(
                                        title, fallback_text, keywords, client_name, client_context=client_context
                                    )
                                except Exception as pw_err:
                                    logger.error(f"Paywall LLM relevance check failed: {pw_err}")
                                    pw_relevant = False
                                
                                if pw_relevant:
                                    logger.info(f"Paywalled article '{title}' deemed RELEVANT by LLM.")
                                    return {
                                        "art_data": {
                                            "title": title,
                                            "url": resolved_url,
                                            "agency": agency,
                                            "summary": fallback_text,
                                            "publication_category": pub_cat,
                                            "is_paywalled": True
                                        },
                                        "is_relevant_kw": True,
                                        "is_semantic_relevant": True
                                    }
                        
                        return {
                            "art_data": {
                                "title": title,
                                "url": resolved_url,
                                "agency": agency,
                                "summary": desc or "No meaningful text extracted from article.",
                                "publication_category": pub_cat,
                                "is_paywalled": is_pw
                            },
                            "is_relevant_kw": True,
                            "is_semantic_relevant": False
                        }
                        
                    # 8. Cosine Similarity Pre-Filter
                    from scraper.similarity import evaluate_similarity_pre_filter, SIM_DROP_THRESHOLD
                    sim_score = evaluate_similarity_pre_filter(
                        title, body_text, keywords, client_context or ""
                    )
                    # Cosine similarity pre-filter drop is temporarily disabled for maximum recall
                    logger.info(f"Cosine similarity pre-filter drop bypassed for '{title}' (score: {sim_score:.4f} < {SIM_DROP_THRESHOLD}).")
                    # Original similarity filter (commented out to allow switching back):
                    # if sim_score < SIM_DROP_THRESHOLD:
                    #     logger.info(f"Cosine similarity pre-filter drop for '{title}' (score: {sim_score:.4f} < {SIM_DROP_THRESHOLD}). Skipping LLM.")
                    #     with get_db_sync() as db:
                    #         db.merge(IrrelevantArticle(
                    #             url=normalized_url, 
                    #             title=title, 
                    #             description=desc or body_text[:200],
                    #             rejection_reason=f"Similarity pre-filter drop (score: {sim_score:.4f} < {SIM_DROP_THRESHOLD})",
                    #             relevance_score=sim_score,
                    #             last_seen_at=datetime.now()
                    #         ))
                    #         db.commit()
                    #     _increment_funnel_metric(job_id, "pre_filter_dropped")
                    #     from scraper.search_utils import match_publication_category
                    #     return {
                    #         "art_data": {
                    #             "title": title,
                    #             "url": resolved_url,
                    #             "agency": agency,
                    #             "summary": desc or (body_text[:200] + "...") if body_text else "Similarity pre-filter drop.",
                    #             "publication_category": match_publication_category(agency, resolved_url),
                    #             "is_paywalled": False
                    #         },
                    #         "is_relevant_kw": True,
                    #         "is_semantic_relevant": False
                    #     }

                    # 9. Relevance Check (Asymmetric & Ensembling)
                    is_semantic_relevant = False
                    verdict = "uncertain"
                    reason = ""
                    score = 0.5
                    from scraper.llm import check_relevance_with_groq
                    try:
                        is_semantic_relevant, verdict, reason, score = check_relevance_with_groq(
                            title, body_text, keywords, client_name, client_context=client_context
                        )
                    except Exception as rel_err:
                        logger.error(f"Relevance verification error for '{title}': {rel_err}")
                        is_semantic_relevant = True # Fallback to True if API fails
                        verdict = "uncertain"
                        reason = f"Exception: {rel_err}"
                        score = 0.5
                        
                    if not is_semantic_relevant:
                        logger.info(f"Relevance check: article '{title}' is not relevant (verdict: {verdict}, score: {score}). Skipping.")
                        with get_db_sync() as db:
                            db.merge(IrrelevantArticle(
                                url=normalized_url,
                                title=title,
                                description=desc or body_text[:200],
                                rejection_reason=reason,
                                relevance_score=score,
                                last_seen_at=datetime.now()
                            ))
                            db.commit()
                        _increment_funnel_metric(job_id, "relevance_no")
                        from scraper.search_utils import match_publication_category
                        return {
                            "art_data": {
                                "title": title,
                                "url": resolved_url,
                                "agency": agency,
                                "summary": desc or (body_text[:200] + "...") if body_text else "Semantically irrelevant.",
                                "publication_category": match_publication_category(agency, resolved_url),
                                "is_paywalled": False
                            },
                            "is_relevant_kw": True,
                            "is_semantic_relevant": False
                        }
                        
                    _increment_funnel_metric(job_id, "relevance_yes")
                        
                    # 9. Summarize & Enrich
                    logger.info(f"Enriching and summarizing article: {title}")
                    summary_text = ""
                    author_name = None
                    extra_meta = {}
                    try:
                        from scraper.parser import extract_author_v2
                        author_metadata = extract_author_v2(html_content)
                        html_top, html_bottom = "", ""
                        try:
                            import re
                            body_start_match = re.search(r"<body.*?>", html_content[:15000], re.I)
                            body_start_idx = body_start_match.end() if body_start_match else 0
                            html_top = html_content[body_start_idx:body_start_idx + 3000]
                            html_bottom = html_content[-3000:]
                        except Exception as e_snip:
                            logger.warning(f"Snippeting failed inside client report process for {resolved_url}: {e_snip}")
                        
                        extra_meta = {
                            "author_metadata": author_metadata,
                            "html_snippets": {
                                "top": html_top,
                                "bottom": html_bottom
                            }
                        }
                        
                        enrichment = perform_full_enrichment_sync(
                            body=body_text,
                            title=title,
                            url=resolved_url,
                            sector=client_name,
                            context_agency=agency,
                            extra_metadata=extra_meta
                        )
                        if enrichment:
                            if enrichment.get("summary"):
                                summary_text = enrichment["summary"]
                            agency = enrichment.get("agency") or agency
                            author_name = enrichment.get("author")
                    except Exception as e:
                        logger.error(f"LLM Enrichment failed for '{title}': {e}")
                        
                    if not summary_text:
                        summary_text = body_text[:300] + "..."
                        
                    _increment_funnel_metric(job_id, "summarized_count")
                    
                    from scraper.search_utils import match_publication_category
                    pub_category = match_publication_category(agency, resolved_url)
                    extra_meta["publication_category"] = pub_category
                        
                    # 10. Cache to DB
                    try:
                        val_dict = {
                            "title": title,
                            "url": normalized_url,
                            "resolved_url": resolved_url,
                            "full_body": body_text,
                            "summary": summary_text,
                            "author": author_name,
                            "agency": agency,
                            "published_at": datetime.now(),
                            "sector": f"{client_name} - {section_name}",
                            "region": "india",
                            "user_id": f"client_{client_id}",
                            "scraped_at": datetime.now(),
                            "extra_metadata": extra_meta
                        }
                        with get_db_sync() as db:
                            existing = db.execute(
                                select(Article)
                                .where(Article.url == normalized_url)
                                .where(Article.user_id == f"client_{client_id}")
                            ).scalars().first()
                            if existing:
                                for k, v in val_dict.items():
                                    setattr(existing, k, v)
                            else:
                                db.add(Article(**val_dict))
                            db.commit()
                    except Exception as dberr:
                        logger.error(f"Failed to cache scraped article to database: {dberr}")
                        
                    art_data = {
                        "title": title,
                        "url": resolved_url,
                        "agency": agency,
                        "summary": summary_text,
                        "publication_category": pub_category,
                        "is_paywalled": False
                    }
                    
                    return {
                        "art_data": art_data,
                        "is_relevant_kw": True,
                        "is_semantic_relevant": True
                    }
                except Exception as art_err:
                    logger.error(f"Error processing article '{title}': {art_err}", exc_info=True)
                    return None

            total_to_process = len(unique_discovered)
            _update_progress(f"Processing and filtering {total_to_process} discovered articles in '{section_name}'...")
            logger.info(f"Starting concurrent processing of {total_to_process} articles for section '{section_name}'")
            
            art_tuples = [(art, idx) for idx, art in enumerate(unique_discovered)]
            processed_count = 0
            
            # Run up to 8 threads per section (sections now run in parallel, so 8 keeps total threads safe)
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = {executor.submit(_process_single_article, t): t for t in art_tuples}
                for future in as_completed(futures):
                    processed_count += 1
                    _update_progress(f"Processed article {processed_count}/{total_to_process} in '{section_name}'...")
                    try:
                        res = future.result()
                        if res:
                            art_data = res["art_data"]
                            is_relevant_kw = res["is_relevant_kw"]
                            is_semantic_relevant = res["is_semantic_relevant"]
                            
                            if is_relevant_kw:
                                master_section_articles.append(art_data)
                                if is_semantic_relevant:
                                    filtered_section_articles.append(art_data)
                    except Exception as future_err:
                        logger.error(f"Thread task exception: {future_err}")
            
            cat_counts = {"A": 0, "B": 0, "C": 0}
            paywalled_count = 0
            for art in filtered_section_articles:
                cat_counts[art.get("publication_category", "C")] += 1
                if art.get("is_paywalled"):
                    paywalled_count += 1

            _update_progress(
                f"Section '{section_name}' completed. "
                f"Discovered: {total_to_process}, "
                f"Relevant: {len(filtered_section_articles)} (Cat A: {cat_counts['A']}, Cat B: {cat_counts['B']}, Cat C: {cat_counts['C']}), "
                f"Paywalled: {paywalled_count}."
            )
            return section_name, filtered_section_articles, master_section_articles

        # Run all sections in parallel — all sections start simultaneously
        active_processing_sections = {sn: kw for sn, kw in sections_data.items() if kw}
        sec_workers = min(len(active_processing_sections), 5)
        with ThreadPoolExecutor(max_workers=sec_workers) as sec_exe:
            sec_futures = {
                sec_exe.submit(_process_section, sn, kw): sn
                for sn, kw in active_processing_sections.items()
            }
            for fut in as_completed(sec_futures):
                try:
                    sn, filtered, master = fut.result()
                    report_data_filtered[sn] = filtered
                    report_data_master[sn] = master
                except Exception as sec_err:
                    logger.error(f"Section processing failed: {sec_err}", exc_info=True)

        # Check if we got any articles at all
        total_filtered_count = sum(len(articles) for articles in report_data_filtered.values())
        has_articles = total_filtered_count > 0
        if not has_articles:
            logger.info("No relevant articles found for any section. A briefing report indicating this will still be generated.")
            
        # 6. Generate DOCX files
        _update_progress("Compiling Word briefing documents (Master and Filtered)...")
        date_str = datetime.now().strftime("%d-%m-%Y")
        reports_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
        os.makedirs(reports_dir, exist_ok=True)
        
        timestamp_suffix = f"{date_str}_{int(datetime.now().timestamp())}"
        
        docx_filename_filtered = f"{client_name.replace(' ', '_')}_Filtered_{timestamp_suffix}.docx"
        docx_path_filtered = os.path.join(reports_dir, docx_filename_filtered)
        
        docx_filename_master = f"{client_name.replace(' ', '_')}_Master_{timestamp_suffix}.docx"
        docx_path_master = os.path.join(reports_dir, docx_filename_master)
        
        logger.info(f"Generating Filtered Word report: {docx_path_filtered}")
        generate_docx_report(
            client_name=client_name,
            date_str=datetime.now().strftime("%B %d, %Y"),
            data=report_data_filtered,
            output_path=docx_path_filtered,
            template_path=template_path
        )
        
        logger.info(f"Generating Master Word report: {docx_path_master}")
        generate_docx_report(
            client_name=f"{client_name} (Master)",
            date_str=datetime.now().strftime("%B %d, %Y"),
            data=report_data_master,
            output_path=docx_path_master,
            template_path=template_path
        )
        
        # 7. Upload to Google Drive/Docs & Share
        google_doc_url_filtered = None
        google_doc_url_master = None
        
        if os.path.exists(docx_path_filtered):
            _update_progress("Uploading Filtered report to Google Drive...")
            logger.info("Uploading Filtered report to Google Drive...")
            try:
                google_doc_url_filtered = upload_docx_to_google_doc(
                    docx_path=docx_path_filtered,
                    client_name=client_name,
                    date_str=datetime.now().strftime("%B %d, %Y"),
                    recipients=all_emails,
                    doc_suffix=""
                )
            except Exception as e:
                logger.error(f"Failed to upload Filtered report to Google Docs: {e}")
                
        if os.path.exists(docx_path_master):
            _update_progress("Uploading Master report to Google Drive...")
            logger.info("Uploading Master report to Google Drive...")
            try:
                google_doc_url_master = upload_docx_to_google_doc(
                    docx_path=docx_path_master,
                    client_name=client_name,
                    date_str=datetime.now().strftime("%B %d, %Y"),
                    recipients=all_emails,
                    doc_suffix=" (Master)"
                )
            except Exception as e:
                logger.error(f"Failed to upload Master report to Google Docs: {e}")
                
        # 8. Send Email notification
        _update_progress("Sending daily briefing email...")
        logger.info(f"Sending report email to: {all_emails}")
        email_sent = send_report_email(
            recipient_emails=all_emails,
            client_name=client_name,
            docx_path_filtered=docx_path_filtered,
            docx_path_master=docx_path_master,
            google_doc_url_filtered=google_doc_url_filtered,
            google_doc_url_master=google_doc_url_master,
            has_articles=has_articles
        )
        
        if not email_sent:
            logger.warning("Report generated but email notification failed to send (SMTP connection error).")
            with get_db_sync() as db:
                run_log = db.execute(select(ClientRunLog).where(ClientRunLog.id == run_log_id)).scalar_one_or_none()
                current_log = run_log.progress_message or ""
                timestamp = datetime.now().strftime("%H:%M:%S")
                final_msg = f"[{timestamp}] Completed with warning: Email failed to send."
                updated_log = f"{current_log}\n{final_msg}" if current_log else final_msg
                db.execute(
                    update(ClientRunLog)
                    .where(ClientRunLog.id == run_log_id)
                    .values(
                        status="completed",
                        generated_file_path=google_doc_url_filtered or docx_path_filtered,
                        progress_message=updated_log,
                        error_message="Email notification failed to send (SMTP connection timeout).",
                        completed_at=datetime.utcnow()
                    )
                )
                db.execute(
                    update(Client)
                    .where(Client.id == client_id)
                    .values(last_run_at=datetime.utcnow())
                )
                db.commit()
            return True
            
        # Update run log status to completed
        with get_db_sync() as db:
            run_log = db.execute(select(ClientRunLog).where(ClientRunLog.id == run_log_id)).scalar_one_or_none()
            current_log = run_log.progress_message or ""
            timestamp = datetime.now().strftime("%H:%M:%S")
            final_msg = f"[{timestamp}] Completed successfully."
            updated_log = f"{current_log}\n{final_msg}" if current_log else final_msg
            db.execute(
                update(ClientRunLog)
                .where(ClientRunLog.id == run_log_id)
                .values(
                    status="completed",
                    generated_file_path=google_doc_url_filtered or docx_path_filtered,
                    progress_message=updated_log,
                    completed_at=datetime.utcnow()
                )
            )
            db.execute(
                update(Client)
                .where(Client.id == client_id)
                .values(last_run_at=datetime.utcnow())
            )
            db.commit()
            
        logger.info(f"Client Report Task completed successfully for client {client_id}")
        return True
        
    except Exception as e:
        error_msg = str(e)
        full_tb = traceback.format_exc()
        logger.error(f"Client report task failed for client {client_id}: {error_msg}\n{full_tb}", exc_info=True)
        
        # Trigger fail-safe email alert immediately
        try:
            send_error_alert_email(
                client_name=client_name,
                error_details=f"Exception: {error_msg}\n\nTraceback:\n{full_tb}"
            )
        except Exception as alert_err:
            logger.error(f"Failed to send fail-safe email alert for client {client_id}: {alert_err}")
            
        # Update run log status to failed
        if run_log_id:
            try:
                with get_db_sync() as db:
                    run_log = db.execute(select(ClientRunLog).where(ClientRunLog.id == run_log_id)).scalar_one_or_none()
                    current_log = run_log.progress_message or ""
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    final_msg = f"[{timestamp}] Failed: {error_msg}"
                    updated_log = f"{current_log}\n{final_msg}" if current_log else final_msg
                    db.execute(
                        update(ClientRunLog)
                        .where(ClientRunLog.id == run_log_id)
                        .values(
                            status="failed",
                            error_message=error_msg,
                            progress_message=updated_log,
                            completed_at=datetime.utcnow()
                        )
                    )
                    db.commit()
            except Exception as dberr:
                logger.error(f"Failed to write failure log to database: {dberr}")
                
        return False


@celery_app.task(name="scraper.tasks.check_client_schedules")
def check_client_schedules():
    """
    Celery Beat task to check client reporting schedules and trigger runs.
    Runs every 5 minutes.
    """
    from db.database import get_db_sync, Client, ClientRunLog
    from datetime import datetime
    import pytz
    from sqlalchemy import select, desc
    
    # Redis Lock to prevent duplicate runs from concurrent schedulers
    try:
        r = get_redis_sync()
        current_minute = datetime.now().minute
        minute_block = current_minute - (current_minute % 5)
        lock_key = f"lock:scheduler:check:{datetime.now().strftime('%Y-%m-%d-%H')}-{minute_block}"
        if not r.set(lock_key, "1", nx=True, ex=240):
            logger.info("Schedule check already processed by another instance. Skipping.")
            return
    except Exception as lock_err:
        logger.warning(f"Failed to acquire Redis scheduler lock: {lock_err}")
    
    logger.info("Checking client automation schedules...")
    
    with get_db_sync() as db:
        active_clients = db.execute(select(Client).where(Client.is_active == True)).scalars().all()
        
        for client in active_clients:
            try:
                # 1. Parse client timezone
                client_tz = pytz.timezone(client.timezone)
                from datetime import datetime, timedelta
                now_tz = datetime.now(client_tz)
                
                # Skip scheduled runs on weekends (Saturday=5, Sunday=6) in client's timezone
                if now_tz.weekday() in [5, 6]:
                    logger.info(f"Skipping schedule check for client '{client.name}' as it is the weekend ({now_tz.strftime('%A')}).")
                    continue
                
                # 2. Parse scheduled time (format HH:MM)
                sched_hour, sched_min = map(int, client.scheduled_time.split(":"))
                
                # 3. Calculate time differences to check if we are in the 10-minute window
                # We check target time for both today and yesterday to support midnight boundary crossings
                target_today = now_tz.replace(hour=sched_hour, minute=sched_min, second=0, microsecond=0)
                diff_today = (now_tz - target_today).total_seconds() / 60.0
                
                target_yesterday = target_today - timedelta(days=1)
                diff_yesterday = (now_tz - target_yesterday).total_seconds() / 60.0
                
                # Determine if current time falls within 10 minutes after scheduled target time
                is_in_window = (0 <= diff_today < 10) or (0 <= diff_yesterday < 10)
                
                if is_in_window:
                    # Decide which target date this trigger belongs to
                    target_date = target_today.date() if (0 <= diff_today < 10) else target_yesterday.date()
                    
                    # Check if a run has already occurred for this specific target date
                    last_log = db.execute(
                        select(ClientRunLog)
                        .where(ClientRunLog.client_id == client.id)
                        .order_by(desc(ClientRunLog.started_at))
                        .limit(1)
                    ).scalar_one_or_none()
                    
                    already_ran = False
                    if last_log:
                        last_started = last_log.started_at.replace(tzinfo=pytz.utc).astimezone(client_tz) if last_log.started_at.tzinfo else pytz.utc.localize(last_log.started_at).astimezone(client_tz)
                        if last_started.date() == target_date and last_log.status in ["completed", "running"]:
                            already_ran = True
                            
                    if not already_ran:
                        logger.info(f"Scheduling report run for client '{client.name}' (Target Date: {target_date}, Scheduled: {client.scheduled_time} in {client.timezone})")
                        celery_app.send_task(
                            "scraper.tasks.run_client_report_task",
                            args=[client.id]
                        )
            except Exception as e:
                logger.error(f"Error checking schedule for client '{client.name}': {e}")
