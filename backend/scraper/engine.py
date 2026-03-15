"""
Core Scraping Engine: Distributed Systems Edition.
Standardized on SQLAlchemy (async) and Celery-based task decoupling.
"""

import asyncio
import os
import sys
import random
import re
import hashlib
import json
import httpx
import feedparser
import trafilatura
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from urllib.parse import quote_plus
from sqlalchemy import select, update, insert, text, delete
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from scraper.parser import extract_body, extract_author, extract_date, is_junk_body
from scraper.google_news import resolve_google_news_url

from db.database import get_db, Article, ScrapeJob
from scraper.config import SECTOR_KEYWORDS, REGION_MAP, SEARCH_MODIFIERS, USER_AGENTS

# --- Windows Support ---
if sys.platform == 'win32':
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except:
        pass

# --- Logging (D-6: JSON Logging) ---
import logging
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "time": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "msg": record.getMessage(),
            "logger": record.name
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)

handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(JsonFormatter())

logging.basicConfig(
    level=logging.INFO,
    handlers=[handler]
)
logger = logging.getLogger("ENGINE")

# --- Exception Hierarchy (Remediation C-3) ---
class NexusBaseError(Exception):
    """Base exception for all NEXUS-specific errors."""
    pass

class ProxyFailureError(NexusBaseError):
    """Raised when proxy authentication or connection fails (403/429)."""
    pass

class RateLimitError(NexusBaseError):
    """Raised when external APIs (Groq, Google) rate limit the request."""
    pass

class ArticleFetchError(NexusBaseError):
    """Raised when article content cannot be retrieved after retries."""
    pass

# --- Resource Pooling ---
_browser_sem = None
_shared_p = None
_shared_browser = None
_browser_lock = asyncio.Lock()
_articles_processed = 0 # Counter for browser recycling (C-5)
_proxies = []

# --- Redis Cache (Remediation C-6) ---
import redis.asyncio as redis
_redis_client = None

async def get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
    return _redis_client

def load_proxies():
    global _proxies
    if not _proxies:
        # Static files
        for fname in ["webshare_proxies.txt", "Webshare 10 proxies.txt"]:
            fpath = os.path.join(os.path.dirname(__file__), "..", fname)
            if os.path.exists(fpath):
                with open(fpath, "r") as f:
                    for line in f:
                        parts = line.strip().split(":")
                        if len(parts) == 4:
                            # Standardized as full URL strings
                            _proxies.append(f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}")
    
    # Backconnect gateway (Railway requirement)
    backconnect = os.getenv("WEBSHARE_PROXY_URL")
    if backconnect:
        if "@" not in backconnect and os.getenv("WEBSHARE_PROXY_USER"):
            user = os.getenv("WEBSHARE_PROXY_USER")
            pw = os.getenv("WEBSHARE_PROXY_PASS")
            backconnect = f"http://{user}:{pw}@{backconnect.replace('http://', '')}"
        
        if not backconnect.startswith("http"):
            backconnect = f"http://{backconnect}"
            
        _proxies = [backconnect]
        log(f"PROXY: Using backconnect rotating gateway: {backconnect}")
    
    if not _proxies:
        log("WARNING: No proxies loaded. Scraper will use direct connection.")
        
    return _proxies

async def get_browser_instance():
    """Global browser pooler with recycling logic (C-5)."""
    global _shared_p, _shared_browser, _articles_processed
    async with _browser_lock:
        # Recycle browser every 100 articles
        if _shared_browser is not None and _articles_processed >= 100:
            log(f"BROWSER: Recycling instance after {_articles_processed} articles.")
            await _shared_browser.close()
            _shared_browser = None
            _articles_processed = 0

        if _shared_browser is None or not _shared_browser.is_connected():
            if _shared_p is None:
                _shared_p = await async_playwright().start()
            
            # Use random proxy if available
            proxies = load_proxies()
            proxy_args = {}
            if proxies:
                p_url = random.choice(proxies)
                # Playwright launch likes dict or Server URL string
                proxy_args["proxy"] = {"server": p_url}
                log(f"BROWSER: Launching with proxy server.")

            _shared_browser = await _shared_p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
                **proxy_args
            )
            log("BROWSER: Shared instance launched.")
        
        _articles_processed += 1
        return _shared_browser

async def shutdown_browser():
    global _shared_p, _shared_browser
    async with _browser_lock:
        if _shared_browser:
            await _shared_browser.close()
            _shared_browser = None
        if _shared_p:
            await _shared_p.stop()
            _shared_p = None

def get_browser_semaphore():
    global _browser_sem
    if _browser_sem is None:
        # Limit to 3 concurrent browsers/contexts to prevent OOM
        _browser_sem = asyncio.Semaphore(int(os.getenv("MAX_CONCURRENT_BROWSERS", "3")))
    return _browser_sem

def log(msg: str):
    logger.info(msg)

# --- Helpers ---
def random_ua() -> str:
    return random.choice(USER_AGENTS)

async def update_phase_status(db, job_id, phase_name, status):
    """Update job phase stats using SQLAlchemy."""
    try:
        res = await db.execute(select(ScrapeJob.phase_stats).where(ScrapeJob.id == job_id))
        phase_stats_raw = res.scalar()
        
        current_stats = {}
        if phase_stats_raw:
            try:
                current_stats = json.loads(phase_stats_raw)
            except:
                pass
        
        current_stats[phase_name] = {
            "status": status,
            "updated_at": datetime.now().isoformat()
        }
        
        await db.execute(
            update(ScrapeJob)
            .where(ScrapeJob.id == job_id)
            .values(phase_stats=json.dumps(current_stats), current_phase=phase_name)
        )
        await db.commit()
    except Exception as e:
        log(f"Error updating phase status: {e}")

# ─── Discovery Phase ──────────────────────────────────────────────────────────

async def discover_articles(keywords: List[str], day: date, geo: str, region_name: str, job_id: str, cumulative: set = None) -> List[dict]:
    """Hyper-Scale Discovery via Google News RSS Loop with 3-Hour Granular Windows."""
    from scraper.config import SEARCH_MODIFIERS, REGION_MAP
    articles = []
    seen_urls = set()
    
    # Identify cities for local targeting
    region_data = REGION_MAP.get(region_name.lower(), {"geo": "US", "cities": []})
    cities = region_data.get("cities", [])
    
    # Generate 3-hour windows (8 blocks per day)
    windows = [
        ("00:00:00", "03:00:00"), ("03:00:00", "06:00:00"), 
        ("06:00:00", "09:00:00"), ("09:00:00", "12:00:00"),
        ("12:00:00", "15:00:00"), ("15:00:00", "18:00:00"), 
        ("18:00:00", "21:00:00"), ("21:00:00", "23:59:59")
    ]

    log(f"Starting 3-hour granular discovery for {day} ({region_name})")
    proxies_list = load_proxies()

    for start_t, end_t in windows:
        log(f"Processing 3-hour window: {start_t} to {end_t}")
        
        # Select proxy for this window to spread load
        proxy_url = None
        if proxies_list:
            proxy_url = random.choice(proxies_list)
            log(f"  [Window {start_t}] Using randomized proxy gateway.")

        async with httpx.AsyncClient(
            timeout=30, 
            follow_redirects=True,
            proxy=proxy_url if proxy_url else None
        ) as client:
            async def fetch_rss(q, start_time, end_time):
                full_after = f"{day.isoformat()}T{start_time}"
                full_before = f"{day.isoformat()}T{end_time}"
                
                g_url = f"https://news.google.com/rss/search?q={quote_plus(q)}+after:{full_after}+before:{full_before}&gl={geo}"
                try:
                    await asyncio.sleep(random.uniform(0.5, 2.0))
                    resp = await client.get(g_url, headers={"User-Agent": random_ua()})
                    if resp.status_code == 200:
                        feed = feedparser.parse(resp.text)
                        batch_entries = 0
                        for e in feed.entries:
                            link = e.get("link")
                            if not link or link in seen_urls: continue
                            seen_urls.add(link)
                            batch_entries += 1
                            
                            pub_date_str = day.isoformat()
                            if "published_parsed" in e:
                                try:
                                    dt = datetime(*e.published_parsed[:6])
                                    pub_date_str = dt.isoformat()
                                except: pass
                            elif "published" in e:
                                pub_date_str = e.published
    
                            articles.append({
                                "title": e.get("title", ""),
                                "url": link,
                                "published_at": pub_date_str, 
                                "agency": e.get("source", {}).get("title", ""),
                            })
                        if batch_entries > 0:
                            log(f"  [Window {start_time}] Found {batch_entries} articles for '{q}'")
                    elif resp.status_code in [403, 429, 503]:
                        log(f"  [Window {start_time}] Proxy/Rate limit error ({resp.status_code}) for '{q}'")
                        raise ProxyFailureError(f"HTTP {resp.status_code}")
                    else:
                        resp.raise_for_status()
                except ProxyFailureError:
                    raise
                except Exception as e:
                    log(f"Discovery Error for {q}: {e}")
            
            # Construct query list for this window
            window_queries = []
            for kw in keywords:
                window_queries.append(kw)
                for mod in random.sample(SEARCH_MODIFIERS, min(len(SEARCH_MODIFIERS), 10)):
                    window_queries.append(f"{kw} {mod}")
                if cities:
                    for city in random.sample(cities, min(len(cities), 3)):
                        window_queries.append(f"{kw} {city}")

            # Process window queries in small parallel batches
            batch_size = 5
            for i in range(0, len(window_queries), batch_size):
                batch = window_queries[i:i+batch_size]
                await asyncio.gather(*[fetch_rss(q, start_t, end_t) for q in batch])
                await asyncio.sleep(random.uniform(1, 4))

    log(f"Completed discovery for {day}. Unique articles found: {len(seen_urls)}")
    if cumulative is not None: cumulative.update(seen_urls)
    return articles

# ─── Scraper Phase ────────────────────────────────────────────────────────────

async def scrape_only(article: dict, job_id: str, sector: str, region: str, user_id: str) -> Optional[int]:
    """Extraction Node: Playwright I/O ONLY."""
    # C-X: Skip RSS feeds that sometimes leak into Google News entries
    if "/rss/" in article["url"] or "rss=1" in article["url"]:
        log(f"Skipping RSS feed URL: {article['url']}")
        # Increment progress even for skipped RSS
        async with get_db() as db:
            await db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(total_scraped=ScrapeJob.total_scraped + 1))
            await db.commit()
        return None

    try:
        url = article["url"]
        # Default date from discovery
        pub_at_str = article.get("published_at")
        try:
            # Try to parse if it's already a string or datetime
            if isinstance(pub_at_str, str):
                final_pub_at = datetime.fromisoformat(pub_at_str.replace('Z', '+00:00'))
            else:
                final_pub_at = datetime.now() # Fallback
        except:
            final_pub_at = datetime.now()

        if "news.google.com/rss/articles" in url:
            res = await resolve_google_news_url(url)
            if res: url = res

        sem = get_browser_semaphore()
        async with sem:
            browser = await get_browser_instance()
            context = None
            try:
                # Optimized context creation from shared browser
                context = await browser.new_context(
                    user_agent=random_ua(),
                    viewport={'width': 1280, 'height': 720}
                )
                page = await context.new_page()
                await Stealth().apply_stealth_async(page)
                
                # Optimized navigation/extraction
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                
                if "consent.google.com" in page.url:
                    try:
                        await page.click('button[aria-label="Accept all"]')
                        await page.wait_for_load_state("domcontentloaded")
                    except: pass

                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1000)
                html = await page.content()
                
                # C-3: Detect proxy deaths/silent failures in browser
                if "403 Forbidden" in html or "429 Too Many Requests" in html or "Access Denied" in html:
                    raise ProxyFailureError("Browser detected block page")

                body = extract_body(html)
                author = extract_author(html)
                
                # Refine publication date from HTML
                extracted_date = extract_date(html)
                if extracted_date:
                    final_pub_at = extracted_date
            except Exception as outer_e:
                print(f"DEBUG: Scrape failed: {outer_e}")
                body, author = "", None
            finally:
                if context: await context.close()

        # --- Filtering & Relevance Logic ---
        # --- Filtering & Resource Management ---
        # User requested max discovery (2k+), so we relax filtering significantly.
        # We only reject if body is completely empty.
        
        # 1. Strict 24h Date Check (Keep this to ensure freshness unless user says otherwise)
        now = datetime.now()
        if final_pub_at.tzinfo: now = now.astimezone(final_pub_at.tzinfo)
        date_invalid = (now - final_pub_at) > timedelta(hours=24)

        if not body or date_invalid:
            async with get_db() as db:
                await db.execute(delete(Article).where(Article.url == article["url"]))
                log(f"Removed placeholder (EmptyBody:{not body}, DateInvalid:{date_invalid}): {article['title']}")
                
                # Increment progress even for rejected articles
                await db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(total_scraped=ScrapeJob.total_scraped + 1))
                
                # Check for completion
                job_res = await db.execute(select(ScrapeJob).where(ScrapeJob.id == job_id))
                job = job_res.scalar_one_or_none()
                if job and job.total_scraped >= job.total_found:
                    await db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(status='completed', completed_at=datetime.now()))
                
                await db.commit()
            return None

        async with get_db() as db:
            dialect = db.get_bind().dialect.name
            val_dict = {
                "title": article["title"], "url": article["url"], "full_body": body,
                "author": author, "agency": article.get("agency"),
                "published_at": final_pub_at,
                "sector": brand_to_check if brand_to_check else sector,
                "region": region, "scrape_job_id": job_id, "user_id": user_id
            }

            if dialect == 'postgresql':
                from sqlalchemy.dialects.postgresql import insert as pg_upsert
                stmt = pg_upsert(Article).values(**val_dict)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['url'],
                    set_={"full_body": stmt.excluded.full_body, "scrape_job_id": stmt.excluded.scrape_job_id, "author": stmt.excluded.author, "published_at": stmt.excluded.published_at}
                ).returning(Article.id)
            else:
                from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
                stmt = sqlite_upsert(Article).values(**val_dict)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['url'],
                    set_={"full_body": text("excluded.full_body"), "scrape_job_id": text("excluded.scrape_job_id"), "author": text("excluded.author"), "published_at": text("excluded.published_at")}
                ).returning(Article.id)
            
            # C-6: Pre-screen URL with Redis to avoid UPSERT overhead
            r = await get_redis()
            SEEN_KEY = "nexus:seen_urls"
            res = None
            if await r.sismember(SEEN_KEY, article["url"]):
                log(f"Redis Cache Hit: Skipping UPSERT for {article['url'][:50]}")
                # Still need to increment scraped count if we consider it "done" or just skip
                # Let's say we just skip for performance
            else:
                res = await db.execute(stmt)
                await r.sadd(SEEN_KEY, article["url"])
                await r.expire(SEEN_KEY, 86400) # 24h TTL
            
            # Real-time Progress Tracking
            await db.execute(
                update(ScrapeJob)
                .where(ScrapeJob.id == job_id)
                .values(total_scraped=ScrapeJob.total_scraped + 1)
            )
            
            # Final completion check
            job_res = await db.execute(select(ScrapeJob).where(ScrapeJob.id == job_id))
            job = job_res.scalar_one_or_none()
            if job and job.total_scraped >= job.total_found:
                await db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(status='completed', completed_at=datetime.now()))
                log(f"Job {job_id} Fully Completed.")

            await db.commit()
            return res.scalar() if res else None
    except Exception as e:
        log(f"Scrape failed for {article['url'][:30]}: {e}")
        return None

async def bulk_insert_placeholders(db, job_id: str, articles: List[dict], sector: str, region: str, user_id: str):
    """Insert discovered articles as placeholders for immediate visibility."""
    if not articles: return
    
    brand_to_check = sector if sector != "brand_tracker" else None
    
    dialect = db.get_bind().dialect.name
    for a in articles:
        val_dict = {
            "title": a["title"], "url": a["url"],
            "published_at": datetime.fromisoformat(a["published_at"].replace('Z', '+00:00')) if isinstance(a["published_at"], str) else a["published_at"],
            "sector": brand_to_check if brand_to_check else sector,
            "region": region, "scrape_job_id": job_id, "user_id": user_id,
            "agency": a.get("agency"), "full_body": None # Placeholder
        }
        
        if dialect == 'postgresql':
            from sqlalchemy.dialects.postgresql import insert as pg_upsert
            stmt = pg_upsert(Article).values(**val_dict).on_conflict_do_nothing(index_elements=['url'])
        else:
            from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
            stmt = sqlite_upsert(Article).values(**val_dict).on_conflict_do_nothing(index_elements=['url'])
        
        await db.execute(stmt)
    await db.commit()

# ─── Orchestrator ──────────────────────────────────────────────────────────────

async def run_scrape_job(job_id: str, sector: str, region: str, date_from: date, date_to: date, search_mode: str, user_id: str) -> dict:
    """Discovery Orchestrator. Dispatches Scraper Nodes."""
    log(f"Job {job_id} Start.")
    
    # Convert strings to date objects if necessary (e.g., when coming from Celery)
    if isinstance(date_from, str):
        date_from = date.fromisoformat(date_from)
    if isinstance(date_to, str):
        date_to = date.fromisoformat(date_to)
    
    async with get_db() as db:
        await db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(status='running', started_at=datetime.now(), current_phase="Discovery"))
        await update_phase_status(db, job_id, "Discovery", "running")
        await db.commit()

        keywords = []
        is_brand_mission = False
        
        # Check if sector is a specific WatchedBrand
        from db.database import WatchedBrand
        res_brand = await db.execute(select(WatchedBrand).where(WatchedBrand.name == sector).where(WatchedBrand.user_id == user_id))
        brand_obj = res_brand.scalar_one_or_none()
        
        if brand_obj:
            is_brand_mission = True
            # Build keywords from brand name and its keyword list
            keywords = [brand_obj.name]
            if brand_obj.keywords:
                # Assuming keywords are comma-separated
                keywords.extend([k.strip() for k in brand_obj.keywords.split(",") if k.strip()])
            log(f"Brand Tracking Mission detected for '{sector}'. Identifiers: {keywords}")
        else:
            keywords = SECTOR_KEYWORDS.get(sector.lower(), [sector])

        # Identify region and geo
        geo = REGION_MAP.get(region.lower(), {"geo": "US"})["geo"]
        all_discovered = []
        cumulative = set()

        phase_name = "BrandDiscovery" if is_brand_mission else "Discovery"
        await update_phase_status(db, job_id, phase_name, "running")

        # LOGIC FIX: User wants "strictly 24h window". 
        # If date_from is very old but today is current, we should clarify or cap.
        # However, we will respect the input but log it clearly.
        log(f"Discovery Window: {date_from} to {date_to} ({region}, {geo})")
        
        # Parallel Discovery (C-2)
        dates = []
        curr = date_from
        while curr <= date_to:
            dates.append(curr)
            curr += timedelta(days=1)
        
        log(f"Parallelizing discovery across {len(dates)} days...")
        # Fire all discovery tasks simultaneously
        tasks = [discover_articles(keywords, d, geo, region, job_id, cumulative) for d in dates]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for idx, res in enumerate(results):
            if isinstance(res, Exception):
                log(f"Discovery failed for date {dates[idx]}: {res}")
            elif isinstance(res, list):
                all_discovered.extend(res)
            
        log(f"  ➜ Total unique articles found: {len(cumulative)}")
            
        # Update final found count in DB
        await db.execute(
            update(ScrapeJob)
            .where(ScrapeJob.id == job_id)
            .values(cumulative_found=len(cumulative))
        )
        await db.commit()

        await update_phase_status(db, job_id, phase_name, "completed")
        
        if not all_discovered:
            await db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(status='completed', completed_at=datetime.now(), total_found=0))
            return {"job_id": job_id, "found": 0}

        # IMMEDIATE VISIBILITY: Bulk insert placeholders so they appear in UI right away
        log(f"Inserting {len(all_discovered)} placeholder articles for job {job_id}...")
        await bulk_insert_placeholders(db, job_id, all_discovered, sector, region, user_id)
        
        # Update total found immediately
        await db.execute(
            update(ScrapeJob)
            .where(ScrapeJob.id == job_id)
            .values(total_found=len(all_discovered), current_phase="Scraping")
        )
        await db.commit()

        # Dispatch Celery
        from scraper.tasks import scrape_article_node
        for a in all_discovered:
            # Ensure brand_name is passed for filtering in scrape_only
            a["brand_name"] = sector if sector != "brand_tracker" else None
            scrape_article_node.delay(a, job_id, sector, region, user_id)

        # Do NOT mark as completed here; workers will update status (or we can use a callback)
        # For now, we set status to 'running' and let the frontend poll total_scraped vs total_found
        return {"job_id": job_id, "found": len(all_discovered)}
