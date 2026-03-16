"""
Core Scraping Engine: Distributed Systems Edition.
Standardized on SQLAlchemy (async) and Celery-based task decoupling.
"""

import asyncio
import time
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

# --- Proxy Management & Health (ProxyGuard) ---
class ProxyGuard:
    """Tracks proxy health to prevent wastage and latency on dead gateways."""
    _unhealthy = {} # {proxy_url: expiry_timestamp}
    
    @classmethod
    def mark_unhealthy(cls, proxy_url: str, duration: int = 300):
        if not proxy_url: return
        cls._unhealthy[proxy_url] = time.time() + duration
        log(f"PROXY-GUARD: Blacklisted {proxy_url[:30]}... for {duration}s")
        
    @classmethod
    def is_healthy(cls, proxy_url: str) -> bool:
        if not proxy_url: return True
        expiry = cls._unhealthy.get(proxy_url, 0)
        if time.time() > expiry:
            if proxy_url in cls._unhealthy: del cls._unhealthy[proxy_url]
            return True
        return False

    @classmethod
    def get_healthy_proxy(cls, pool: List[str]) -> Optional[str]:
        healthy = [p for p in pool if cls.is_healthy(p)]
        return random.choice(healthy) if healthy else (random.choice(pool) if pool else None)

def load_proxies():
    global _proxies
    if _proxies:
        return _proxies
        
    # 1. Load from proxy text file if present
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Support multiple possible names
    for fname in ["Webshare 10 proxies.txt", "webshare_proxies.txt"]:
        fpath = os.path.join(base_dir, fname)
        if os.path.exists(fpath):
            with open(fpath, "r") as f:
                for line in f:
                    parts = line.strip().split(":")
                    if len(parts) == 4:
                        _proxies.append(f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}")
    
    # 2. Append dynamically generated rotating proxies from Dashboard pattern
    user_base = os.getenv("WEBSHARE_PROXY_USER", "jxgqvosn")
    pw = os.getenv("WEBSHARE_PROXY_PASS", "symou02ck2bw")
    if user_base and pw:
        # Generate 1-10 indices as shown in dashboard screenshot
        for i in range(1, 11):
            _proxies.append(f"http://{user_base}-{i}:{pw}@p.webshare.io:80")
            
    # 3. Legacy ENV check
    backconnect = os.getenv("WEBSHARE_PROXY_URL")
    if backconnect:
        if "." not in backconnect and ":" not in backconnect:
             backconnect = f"http://{user_base}:{pw}@p.webshare.io:80"
        if not backconnect.startswith("http"):
            backconnect = f"http://{backconnect}"
        _proxies.append(backconnect)

    _proxies = list(dict.fromkeys(_proxies)) # Deduplicate
    if not _proxies:
        log("WARNING: No proxies loaded. Scraper will use direct connection.")
    else:
        log(f"PROXY: Pool initialized with {len(_proxies)} unique gateways.")
        
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
            
            # Use ProxyGuard to select a healthy proxy
            proxies = load_proxies()
            proxy_args = {}
            if proxies:
                p_url = ProxyGuard.get_healthy_proxy(proxies)
                if p_url:
                    proxy_args["proxy"] = {"server": p_url}
                    log(f"BROWSER: Launching with health-verified proxy.")

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

async def is_job_cancelled(job_id: str) -> bool:
    """Check if the job (or whole system) has been flagged for cancellation in Redis."""
    from scraper.llm import get_redis
    try:
        r = await get_redis()
        # 1. Check Global Kill Switch
        if await r.get("nexus:global_stop"):
            log(f"CANCELLATION: Global Stop Flag detected in Redis. Halting all tasks.")
            return True
        # 2. Check Specific Job
        if await r.sismember("nexus:cancelled_jobs", job_id):
            log(f"CANCELLATION: Job {job_id} has been explicitly cancelled by user/system.")
            return True
        return False
    except:
        return False

# --- Relevance Logic ---
def verify_brand_relevance(text: str, keywords: List[str]) -> bool:
    """Strict verification: ensure at least one keyword appears in content."""
    if not text or not keywords:
        return True # Default to inclusive if no filter provided
    
    text_lower = text.lower()
    for kw in keywords:
        if kw.lower() in text_lower:
            return True
            
    # Fuzzy check: If it's a multi-word brand, check if at least 50% of words match
    # (Optional, but helps with Google News fuzziness)
    return False

# ─── Discovery Phase ──────────────────────────────────────────────────────────

async def discover_articles(keywords: List[str], day: date, geo: str, region_name: str, job_id: str, cumulative: set = None) -> List[dict]:
    """Hyper-Scale Discovery via Google News RSS Loop with 3-Hour Granular Windows and Proxy Rotation."""
    from scraper.config import SEARCH_MODIFIERS, REGION_MAP
    articles = []
    seen_urls = set()
    
    region_data = REGION_MAP.get(region_name.lower(), {"geo": "US", "cities": []})
    cities = region_data.get("cities", [])
    
    windows = [
        ("00:00:00", "03:00:00"), ("03:00:00", "06:00:00"), 
        ("06:00:00", "09:00:00"), ("09:00:00", "12:00:00"),
        ("12:00:00", "15:00:00"), ("15:00:00", "18:00:00"), 
        ("18:00:00", "21:00:00"), ("21:00:00", "23:59:59")
    ]

    log(f"Starting 3-hour granular discovery for {day} ({region_name})")
    
    # 1. Prepare global proxy pool once
    proxy_pool = load_proxies()
    if not proxy_pool:
        proxy_pool = [None]
    
    async def fetch_rss_with_rotation(q, start_time, end_time, hl="en-IN", ceid="IN:en", attempt=0):
        if await is_job_cancelled(job_id):
            return

        # Use ProxyGuard for health-aware selection
        current_proxy = ProxyGuard.get_healthy_proxy(proxy_pool)
        
        async with httpx.AsyncClient(timeout=35, follow_redirects=True, proxy=current_proxy) as client:
            full_after = f"{day.isoformat()}T{start_time}"
            full_before = f"{day.isoformat()}T{end_time}"
            domain = REGION_MAP.get(geo, "google.com")
            rss_url = f"https://news.{domain}/rss/search?q={quote_plus(q)}&hl={hl}&gl=IN&ceid={ceid}&start={full_after}&end={full_before}"
            
            try:
                resp = await client.get(rss_url, headers={"User-Agent": random.choice(USER_AGENTS)})
                
                if resp.status_code in [407, 403, 429]:
                    ProxyGuard.mark_unhealthy(current_proxy)
                    if attempt < 3:
                        log(f"  [Discovery] Proxy Error ({resp.status_code}) for '{q}'. Rotating.")
                        await asyncio.sleep(random.uniform(1, 3))
                        return await fetch_rss_with_rotation(q, start_time, end_time, attempt + 1)
                    raise ProxyFailureError(f"HTTP {resp.status_code}")

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
                        
                        articles.append({
                            "title": e.get("title", ""),
                            "url": link,
                            "published_at": pub_date_str, 
                            "agency": e.get("source", {}).get("title", ""),
                        })
                    return # Success
                else:
                    resp.raise_for_status()

            except Exception as exc:
                if attempt < 2:
                    return await fetch_rss_with_rotation(q, start_time, end_time, attempt + 1)
                log(f"Discovery fail for '{q}': {str(exc)[:50]}")

    for start_t, end_t in windows:
        if await is_job_cancelled(job_id): break
        log(f"Processing 3-hour window: {start_t} to {end_t}")
        
        # Determine languages to search in
        search_languages = [{"code": "en-IN", "ceid": "IN:en"}]
        if region_name.lower() == "india":
            from scraper.config import INDIAN_LANGUAGES
            search_languages = INDIAN_LANGUAGES

        # Expand queries for this window
        window_queries = []
        is_brand_tracker = False
        async with get_db() as db:
            from db.database import ScrapeJob
            job_res = await db.execute(select(ScrapeJob.sector).where(ScrapeJob.id == job_id))
            sector_name = job_res.scalar()
            if sector_name:
                from db.database import WatchedBrand
                brand_check = await db.execute(select(WatchedBrand).where(WatchedBrand.name == sector_name))
                if brand_check.scalar_one_or_none():
                    is_brand_tracker = True

        for kw in keywords:
            window_queries.append(kw)
            # Only add modifiers/cities if NOT a brand tracker mission
            if not is_brand_tracker:
                for mod in random.sample(SEARCH_MODIFIERS, min(len(SEARCH_MODIFIERS), 5)):
                    window_queries.append(f"{kw} {mod}")
                if cities:
                    for city in random.sample(cities, min(len(cities), 2)):
                        window_queries.append(f"{kw} {city}")

        # Process queries across all supported languages
        random.shuffle(window_queries)
        for lang in search_languages:
            if await is_job_cancelled(job_id): break
            log(f"  [Discovery] Searching in language: {lang.get('name', lang['code'])}")
            
            for i in range(0, len(window_queries), 5):
                if await is_job_cancelled(job_id): break
                batch = window_queries[i:i+5]
                tasks = [fetch_rss_with_rotation(q, start_t, end_t, hl=lang['code'], ceid=lang['ceid']) for q in batch]
                await asyncio.gather(*tasks)
                await asyncio.sleep(random.uniform(0.5, 1.5))

    log(f"Completed discovery for {day}. Unique articles found: {len(seen_urls)}")
    if cumulative is not None: cumulative.update(seen_urls)
    return articles

# ─── Scraper Phase ────────────────────────────────────────────────────────────

async def scrape_only(article: dict, job_id: str, sector: str, region: str, user_id: str) -> Optional[int]:
    """Extraction Node: Playwright I/O ONLY."""
    # C-X: Check for cancellation before starting expensive browser work
    if await is_job_cancelled(job_id):
        log(f"Scrape cancelled for job {job_id}. Skipping {article['url']}")
        return None

    try:
        url = article["url"]
        
        # 0. Resolve Google News Redirects BEFORE skipping RSS patterns
        # Google News URLs often contain "/rss/" which triggers the skip logic prematurely.
        if "news.google.com/rss/articles" in url:
            res = await resolve_google_news_url(url)
            if res: 
                url = res
                article["url"] = url # Update for downstream use
                log(f"Resolved Google News URL to: {url[:60]}...")

        # 1. Skip genuine RSS feeds/snippets
        # We check the RESOLVED URL now, which is much safer.
        if "/rss/" in url or "rss=1" in url or "feed" in url.lower():
            # Special case: if it resolved to a news article but still has 'rss' in it, 
            # we might want to be careful, but usually real articles don't have /rss/ in path.
            if "news.google.com" not in url: # If it's still google news, it's definitely a redirect/feed
                log(f"Skipping genuine RSS/Feed URL: {url}")
                try:
                    async with get_db() as db:
                        await db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(total_scraped=ScrapeJob.total_scraped + 1))
                        await db.commit()
                except: pass
                return None

        # Determine keywords for relevance filtering
        keywords = []
        async with get_db() as db:
            from db.database import WatchedBrand
            brand_res = await db.execute(select(WatchedBrand).where(WatchedBrand.name == sector).where(WatchedBrand.user_id == user_id))
            brand_obj = brand_res.scalar_one_or_none()
            if brand_obj and brand_obj.keywords:
                keywords = [k.strip() for k in brand_obj.keywords.split(",") if k.strip()]
        
        if not keywords:
            # Fallback for general sector searches or brands without specific keywords
            from scraper.config import SECTOR_KEYWORDS
            if sector.lower() in SECTOR_KEYWORDS:
                keywords.extend(SECTOR_KEYWORDS[sector.lower()])
            elif "brand_name" in article and article["brand_name"]:
                # Use brand name only as a absolute fallback
                keywords = [article["brand_name"]]

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
                # Bandwidth Optimization: Abort non-essential assets (images, css, fonts)
                await page.route("**/*.{png,jpg,gif,css,woff,woff2}", lambda route: route.abort())
                await Stealth().apply_stealth_async(page)
                
                # Phase 1: Navigation
                try:
                    resp = await page.goto(article["url"], wait_until="domcontentloaded", timeout=90000)
                    if not resp or resp.status >= 400:
                        log(f"  [Scraper] Failed to load {article['url']} (Status: {resp.status if resp else 'No Resp'})")
                        return None
                except Exception as e:
                    log(f"  [Scraper] Timeout/Error loading {article['url']}: {e}")
                    return None

                # C-X: Cancel Check 2
                if await is_job_cancelled(job_id): return None

                # Phase 2: Stealth waiting & Scroll
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(random.randint(2000, 4000))
                
                # C-X: Cancel Check 3
                if await is_job_cancelled(job_id): return None

                # Phase 3: Extraction
                content = await page.content()
                
                # C-3: Detect proxy deaths/silent failures in browser
                if "403 Forbidden" in content or "429 Too Many Requests" in content or "Access Denied" in content:
                    log("BROWSER: Detected block page. Highlighting proxy health risk.")
                    raise ProxyFailureError("Browser detected block page")

                body = trafilatura.extract(content, include_comments=False, include_tables=True, no_fallback=False)
                
                # Fallback to BeautifulSoup if extraction is too thin
                if not body or len(body) < 200:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(content, "lxml")
                    for s in soup(["script", "style", "nav", "header", "footer"]):
                        s.decompose()
                    body = soup.get_text(separator="\n", strip=True)
                    if len(body) > 200:
                        log(f"  [Scraper] Trafilatura failed. Used BeautifulSoup fallback for {article['url']}")

                if not body or is_junk_body(body):
                    log(f"  [Scraper] No meaningful content found in {article['url']}")
                    return None
                
                # Metadata extraction
                author = extract_author(content)
                extracted_date = extract_date(content)
                if extracted_date:
                    final_pub_at = extracted_date
                else:
                    # FIX: If date extraction failed, don't default to 'now' for the 24h check.
                    # Use the discovery date if available, or stay with the original 'final_pub_at'
                    pass

            except Exception as outer_e:
                log(f"  [Scraper] Extraction Error for {article['url']}: {outer_e}")
                body, author = "", None
            finally:
                if context: await context.close()

        # --- Filtering & Relevance Logic ---
        
        # 1. Strict Brand Matching (C-X)
        if keywords and not verify_brand_relevance(f"{article['title']} {body}", keywords):
            log(f"Filtering article (Irrelevant to {keywords}): {article['title']}")
            # Proceed to delete placeholder and increment progress
            body = None # Mark as rejected
        
        # 2. Strict 24h Date Check
        now = datetime.now()
        if final_pub_at.tzinfo: now = now.astimezone(final_pub_at.tzinfo)
        date_invalid = (now - final_pub_at) > timedelta(hours=24)

        if not body or date_invalid:
            try:
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
            except Exception as loop_e:
                # Capture and log, but don't crash the task
                if "Event loop is closed" in str(loop_e):
                    log("Cleanup DB call skipped: Event loop already closed.")
                else:
                    log(f"Cleanup DB error: {loop_e}")
            return None

        async with get_db() as db:
            try:
                dialect = db.get_bind().dialect.name
                val_dict = {
                    "title": article["title"], "url": article["url"], "full_body": body,
                    "author": author, "agency": article.get("agency"),
                    "published_at": final_pub_at,
                    "sector": sector,
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
                from scraper.llm import get_redis
                r = await get_redis()
                SEEN_KEY = "nexus:seen_urls"
                res = None
                if await r.sismember(SEEN_KEY, article["url"]):
                    log(f"Redis Cache Hit: Skipping UPSERT for {article['url'][:50]}")
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
            except Exception as db_e:
                if "Event loop is closed" in str(db_e):
                    log("Final DB save skipped: Event loop already closed.")
                else:
                    log(f"Final DB save error: {db_e}")
                return None
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
            # Build keywords ONLY from brand identifier list (EXCLUDE brand name for search)
            if brand_obj.keywords:
                # Assuming keywords are comma-separated
                keywords = [k.strip() for k in brand_obj.keywords.split(",") if k.strip()]
            else:
                # Fallback to brand name ONLY if no keywords are specified, 
                # though user requirements suggest we should rely on keywords.
                keywords = [brand_obj.name]
            log(f"Brand Tracking Mission detected for '{sector}'. Searching via Identifiers: {keywords}")
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
            # C-X: Emergency Stop check inside the loop
            if await is_job_cancelled(job_id):
                log(f"Orchestrator halting dispatch for {job_id} due to cancellation.")
                break
            
            # Ensure brand_name is passed for filtering in scrape_only
            a["brand_name"] = sector if sector != "brand_tracker" else None
            scrape_article_node.delay(a, job_id, sector, region, user_id)

        # Do NOT mark as completed here; workers will update status (or we can use a callback)
        # For now, we set status to 'running' and let the frontend poll total_scraped vs total_found
        return {"job_id": job_id, "found": len(all_discovered)}
