import logging
import json
import httpx
import trafilatura
from datetime import datetime
from celery_app import app as celery_app
from db.database import get_db_sync, Article, ScrapeJob
from scraper.browser import scrape_url
from sqlalchemy import select, update, insert
from scraper.engine import normalize_url
from scraper.llm import get_redis_sync

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
        
        # ─── URL NORMALIZATION & LOCKING ───
        normalized_url = normalize_url(resolved_url)
        lock_key = f"lock:scrape:{normalized_url}"
        r = get_redis_sync()
        
        # Try to acquire lock for 10 minutes to prevent overlaps
        #nx=True means only set if it doesn't exist
        if not r.set(lock_key, job_id, nx=True, ex=600):
            logger.info(f"Task overlap detected for {normalized_url}. Skipping redundant node.")
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
    from utils.email import send_report_email
    from scraper.llm import perform_full_enrichment_sync
    from datetime import date, datetime, timedelta
    import pytz
    
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
            started_at=datetime.now()
        )
        db.add(run_log)
        db.commit()
        db.refresh(run_log)
        run_log_id = run_log.id
        client_name = client.name
        template_path = client.template_path
        
    try:
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
        report_data = {} # {section_name: [list of article dicts]}
        
        # We scrape for the past 24 hours/today
        # In case it's early in the day, we search yesterday and today to be safe
        search_date = date.today()
        
        for section_name, keywords in sections_data.items():
            if not keywords:
                continue
                
            logger.info(f"Discovering articles for section '{section_name}' with keywords: {keywords}")
            # Discover articles
            discovered = discover_articles(
                keywords=keywords,
                day=search_date,
                geo="IN",
                region_name="india",
                job_id=f"client_{client_id}_sec_{section_name}"
            )
            
            # If not enough articles, fallback/extend search to yesterday
            if len(discovered) < 3:
                yesterday = search_date - timedelta(days=1)
                discovered_yesterday = discover_articles(
                    keywords=keywords,
                    day=yesterday,
                    geo="IN",
                    region_name="india",
                    job_id=f"client_{client_id}_sec_{section_name}_yesterday"
                )
                discovered.extend(discovered_yesterday)
                
            # Deduplicate by url
            unique_discovered = []
            seen_urls = set()
            for art in discovered:
                if art["url"] not in seen_urls:
                    unique_discovered.append(art)
                    seen_urls.add(art["url"])
                    
            section_articles = []
            
            # Resolve and scrape each article
            for art in unique_discovered[:10]: # Limit to top 10 articles per section to prevent API/time bloat
                raw_url = art["url"]
                title = art["title"]
                agency = art.get("agency") or "News"
                
                # 1. Resolve URL
                logger.info(f"Resolving Google News URL: {raw_url}")
                resolved_url = resolve_google_news_url_sync(raw_url) or raw_url
                
                # 2. Scrape raw html
                logger.info(f"Scraping content from resolved URL: {resolved_url}")
                html_content = ""
                
                # Try fast extraction with httpx first
                try:
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
                    }
                    with httpx.Client(follow_redirects=True, timeout=10) as client_http:
                        resp = client_http.get(resolved_url, headers=headers)
                        if resp.status_code == 200:
                            html_content = resp.text
                except Exception as e:
                    logger.warning(f"Fast HTTP scrape failed for {resolved_url}: {e}")
                    
                # Fallback to browser scraping if httpx failed or returned small content
                if not html_content or len(html_content) < 1000:
                    try:
                        html_content = scrape_url(resolved_url)
                    except Exception as e:
                        logger.error(f"Browser scrape failed for {resolved_url}: {e}")
                        
                if not html_content:
                    logger.warning(f"Could not fetch HTML content for {resolved_url}. Skipping.")
                    continue
                    
                # 3. Extract text
                body_text = trafilatura.extract(html_content)
                if not body_text or len(body_text) < 200:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html_content, "lxml")
                    for s in soup(["script", "style", "nav", "header", "footer"]):
                        s.decompose()
                    body_text = soup.get_text(separator="\n", strip=True)
                    
                if not body_text or len(body_text) < 100:
                    logger.warning(f"No meaningful text extracted for {resolved_url}. Skipping.")
                    continue
                    
                # 4. Relevance verification
                # Check if at least one keyword is in title or body (case-insensitive)
                lower_title_body = (title + " " + body_text).lower()
                is_relevant = any(kw.lower() in lower_title_body for kw in keywords)
                
                if not is_relevant:
                    logger.info(f"Article '{title}' is not relevant to keywords. Skipping.")
                    continue
                
                # Check semantic relevance with Groq to filter out off-topic / noise articles
                from scraper.llm import check_relevance_with_groq
                if not check_relevance_with_groq(title, body_text, keywords, client_name):
                    logger.info(f"Article '{title}' judged IRRELEVANT by Groq. Skipping.")
                    continue
                    
                # 5. Summarize / Enrich using LLM
                logger.info(f"Enriching and summarizing article: {title}")
                summary_text = ""
                try:
                    # Call LLM helper
                    enrichment = perform_full_enrichment_sync(
                        body=body_text,
                        title=title,
                        url=resolved_url,
                        sector=client_name
                    )
                    if enrichment and enrichment.get("summary"):
                        summary_text = enrichment["summary"]
                        agency = enrichment.get("agency") or agency
                except Exception as e:
                    logger.error(f"LLM Enrichment failed for '{title}': {e}")
                    
                # If LLM failed or returned empty summary, use a simple default truncation
                if not summary_text:
                    summary_text = body_text[:300] + "..."
                    
                section_articles.append({
                    "title": title,
                    "url": resolved_url,
                    "agency": agency,
                    "summary": summary_text
                })
                
            report_data[section_name] = section_articles
            
        # Check if we got any articles at all
        total_articles_count = sum(len(articles) for articles in report_data.values())
        if total_articles_count == 0:
            raise ValueError("No relevant articles found for any section. Report cannot be generated.")
            
        # 6. Generate DOCX file
        date_str = datetime.now().strftime("%d-%m-%Y")
        reports_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
        os.makedirs(reports_dir, exist_ok=True)
        
        docx_filename = f"{client_name.replace(' ', '_')}_Briefing_{date_str}_{int(datetime.now().timestamp())}.docx"
        docx_path = os.path.join(reports_dir, docx_filename)
        
        logger.info(f"Generating Word report: {docx_path}")
        generate_docx_report(
            client_name=client_name,
            date_str=datetime.now().strftime("%B %d, %Y"),
            data=report_data,
            output_path=docx_path,
            template_path=template_path
        )
        
        # 7. Upload to Google Drive/Docs & Share
        google_doc_url = None
        if os.path.exists(docx_path):
            logger.info("Uploading report to Google Drive...")
            try:
                google_doc_url = upload_docx_to_google_doc(
                    docx_path=docx_path,
                    client_name=client_name,
                    date_str=datetime.now().strftime("%B %d, %Y"),
                    recipients=all_emails
                )
            except Exception as e:
                logger.error(f"Failed to upload report to Google Docs: {e}")
                
        # 8. Send Email notification
        logger.info(f"Sending report email to: {all_emails}")
        email_sent = send_report_email(
            recipient_emails=all_emails,
            client_name=client_name,
            docx_path=docx_path,
            google_doc_url=google_doc_url
        )
        
        if not email_sent:
            raise ValueError("Report generated but email notification failed to send.")
            
        # Update run log status to completed
        with get_db_sync() as db:
            db.execute(
                update(ClientRunLog)
                .where(ClientRunLog.id == run_log_id)
                .values(
                    status="completed",
                    generated_file_path=docx_path,
                    completed_at=datetime.now()
                )
            )
            db.execute(
                update(Client)
                .where(Client.id == client_id)
                .values(last_run_at=datetime.now())
            )
            db.commit()
            
        logger.info(f"Client Report Task completed successfully for client {client_id}")
        return True
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Client report task failed for client {client_id}: {error_msg}", exc_info=True)
        
        # Update run log status to failed
        if run_log_id:
            try:
                with get_db_sync() as db:
                    db.execute(
                        update(ClientRunLog)
                        .where(ClientRunLog.id == run_log_id)
                        .values(
                            status="failed",
                            error_message=error_msg,
                            completed_at=datetime.now()
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
    
    logger.info("Checking client automation schedules...")
    
    with get_db_sync() as db:
        active_clients = db.execute(select(Client).where(Client.is_active == True)).scalars().all()
        
        for client in active_clients:
            try:
                # 1. Parse client timezone
                client_tz = pytz.timezone(client.timezone)
                now_tz = datetime.now(client_tz)
                
                # 2. Parse scheduled time (format HH:MM)
                sched_hour, sched_min = map(int, client.scheduled_time.split(":"))
                
                # 3. Check if current time matches scheduled hour & is within schedule window (e.g. 5 minutes)
                # Since celery beat runs every 5 minutes, we match the hour and check if we are in the target window.
                # To prevent double triggering, we check if a run has already occurred today in the client's timezone.
                if now_tz.hour == sched_hour:
                    # Check if the target minute is in the past and close
                    time_diff_minutes = (now_tz.hour * 60 + now_tz.minute) - (sched_hour * 60 + sched_min)
                    
                    if 0 <= time_diff_minutes < 10:
                        # Check if a successful or running job already exists for today
                        # Query last log
                        last_log = db.execute(
                            select(ClientRunLog)
                            .where(ClientRunLog.client_id == client.id)
                            .order_by(desc(ClientRunLog.started_at))
                            .limit(1)
                        ).scalar_one_or_none()
                        
                        already_ran = False
                        if last_log:
                            # Convert last run's started_at to client's timezone
                            last_started = last_log.started_at.replace(tzinfo=pytz.utc).astimezone(client_tz) if last_log.started_at.tzinfo else pytz.utc.localize(last_log.started_at).astimezone(client_tz)
                            if last_started.date() == now_tz.date() and last_log.status in ["completed", "running"]:
                                already_ran = True
                                
                        if not already_ran:
                            logger.info(f"Scheduling report run for client '{client.name}' (Scheduled: {client.scheduled_time} in {client.timezone})")
                            celery_app.send_task(
                                "scraper.tasks.run_client_report_task",
                                args=[client.id]
                            )
            except Exception as e:
                logger.error(f"Error checking schedule for client '{client.name}': {e}")
