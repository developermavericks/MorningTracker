"""
Core Scraping Engine: Distributed Systems Edition.
Standardized on SQLAlchemy (sync) and Celery-based task decoupling.
"""

import time
import os
import sys
import random
import re
import json
import httpx
import feedparser
import trafilatura
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any, Set
from urllib.parse import quote
from sqlalchemy import select, update, insert, text, delete
from gevent.pool import Pool
from scraper.network import NetworkHandler
# from playwright.sync_api import sync_playwright
# from playwright_stealth import Stealth
from scraper.parser import extract_body, extract_author, extract_author_v2, extract_date, is_junk_body
from scraper.sitemap import SitemapManager, DEFAULT_INDIA_SITEMAPS
from scraper.llm import get_redis_sync
from scraper.orchestrator import update_phase_status

from db.database import get_db_sync, Article, ScrapeJob
from scraper.config import SECTOR_KEYWORDS, REGION_MAP, SEARCH_MODIFIERS, USER_AGENTS

# --- Logging ---
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

# --- Exceptions ---
class NexusBaseError(Exception): pass
class ProxyFailureError(NexusBaseError): pass
class RateLimitError(NexusBaseError): pass
class ArticleFetchError(NexusBaseError): pass

from scraper.network import NetworkHandler, ProxyGuard, load_proxies

def log(msg: str):
    logger.info(msg)

def random_ua() -> str:
    return random.choice(USER_AGENTS)

# update_phase_status moved to orchestrator.py

def is_job_cancelled(job_id: str) -> bool:
    from scraper.llm import get_redis_sync
    try:
        r = get_redis_sync()
        if r.get("nexus:global_stop") or r.sismember("nexus:cancelled_jobs", job_id):
            return True
        return False
    except:
        return False

def verify_brand_relevance(text: str, keywords: List[str]) -> bool:
    if not text or not keywords: return True
    text_lower = text.lower()
    for kw in keywords:
        if kw.lower() in text_lower: return True
    return False

# ─── Discovery Phase ───

def discover_articles(keywords: List[str], day: date, geo: str, region_name: str, job_id: str, cumulative: set = None) -> List[dict]:
    articles = []
    seen_urls = set()
    proxy_pool = load_proxies() or []
    
    def fetch_rss(q, start_time, end_time, hl="en-IN", ceid="IN:en"):
        if is_job_cancelled(job_id): return
        
        is_today = day >= date.today()
        domain = "google.com" # standard for news
        if is_today:
            # Format requested by user: q={query} when:1d
            # Note: Using quote() instead of quote_plus() to ensure space is %20 (strictly correct standard)
            full_q = f"{q} when:1d"
            rss_url = f"https://news.{domain}/rss/search?q={quote(full_q)}&hl={hl}&gl=IN&ceid={ceid}"
        else:
            date_str = day.strftime("%m/%d/%Y")
            tbs = f"cdr:1,cd_min:{date_str},cd_max:{date_str},sbd:1"
            # Note: Using quote() instead of quote_plus() to ensure space is %20
            rss_url = f"https://news.{domain}/rss/search?q={quote(q)}&hl={hl}&gl=IN&ceid={ceid}&tbs={quote(tbs)}"
        
        try:
            proxy = ProxyGuard.get_healthy_proxy(proxy_pool)
            xml_content = NetworkHandler.get_google_rss(rss_url, proxy=proxy)
            if not xml_content:
                if proxy:
                    ProxyGuard.mark_unhealthy(proxy)
                return

            feed = feedparser.parse(xml_content)
            for entry in feed.entries:
                link = entry.link
                if link not in seen_urls and (cumulative is None or link not in cumulative):
                    parsed_date = None
                    if hasattr(entry, 'published_parsed'):
                        parsed_date = datetime.fromtimestamp(time.mktime(entry.published_parsed)).date()
                    
                    if is_today:
                        if parsed_date and (day - parsed_date).days > 1:
                            continue
                    elif parsed_date and parsed_date != day:
                        continue
                        
                    pub_date_str = day.isoformat()
                    if hasattr(entry, 'published_parsed'):
                        try: pub_date_str = datetime(*entry.published_parsed[:6]).isoformat()
                        except: pass

                    articles.append({"title": entry.title, "url": link, "published_at": pub_date_str, "agency": entry.source.title if hasattr(entry, 'source') else "Google News"})
                    seen_urls.add(link)
        except Exception as exc:
            log(f"Discovery fail for '{q}': {exc}")

    search_languages = [{"code": "en-IN", "ceid": "IN:en"}]
    with get_db_sync() as db:
        job_res = db.execute(select(ScrapeJob.sector).where(ScrapeJob.id == job_id))
        sector_name = job_res.scalar() or "Technology"
        
        # if region_name.lower() == "india":
        #    from scraper.config import INDIAN_LANGUAGES
        #    search_languages = INDIAN_LANGUAGES

        # Base queries: Start with exact keywords provided
        window_queries = [kw for kw in keywords]
        
        # ADD BRAND NAME (SECTOR) AS A SAFETY NET (captured broadly)
        # if sector_name and sector_name not in window_queries:
        #    window_queries.append(sector_name)
        #    # Also try brand + "India" for geo-specificity if it's the India region
        #    if region_name.lower() == "india" and f"{sector_name} India" not in window_queries:
        #        window_queries.append(f"{sector_name} India")

        is_brand_tracker = False
        from db.database import WatchedBrand
        if db.execute(select(WatchedBrand).where(WatchedBrand.name == sector_name)).first():
            is_brand_tracker = True
    
    if not is_brand_tracker:
        for kw in keywords:
            for mod in random.sample(SEARCH_MODIFIERS, min(len(SEARCH_MODIFIERS), 5)): 
                window_queries.append(f"{kw} {mod}")
    
    random.shuffle(window_queries)
    
    # Discovery Acceleration: Parallelize with a larger pool (now that we have a semaphore on network requests)
    discovery_pool = Pool(10)
    for lang in search_languages:
        if is_job_cancelled(job_id): break
        for q in window_queries:
            if is_job_cancelled(job_id): break
            discovery_pool.spawn(fetch_rss, q, "00:00:00", "23:59:59", hl=lang['code'], ceid=lang['ceid'])
    
    discovery_pool.join()

    if cumulative is not None: cumulative.update(seen_urls)
    return articles

# ─── High-Throughput Discovery (Scaling Strategy) ───

async def discover_articles_scaling(job_id: str, sectors: List[str] = None) -> List[dict]:
    """
    Scaling Discovery: Uses SitemapManager for parallel multi-sector scanning.
    """
    update_phase_status(get_db_sync(), job_id, "Discovery", "running")
    sm = SitemapManager(target_sectors=sectors)
    redis = get_redis_sync()
    
    # Fetch all URLs from sitemaps
    raw_articles = await sm.discover_all(DEFAULT_INDIA_SITEMAPS)
    
    final_articles = []
    seen_in_batch = set()
    
    for a in raw_articles:
        url = a["url"]
        url_hash = hashlib.md5(url.encode()).hexdigest()
        
        # Redis-based deduplication (O(1))
        if redis.sismember("nexus:processed_urls", url_hash) or url in seen_in_batch:
            continue
            
        final_articles.append(a)
        seen_in_batch.add(url)
    
    log(f"Discovery Burst: {len(final_articles)} new articles discovered across {sectors or 'all'} sectors.")
    return final_articles

# ─── Scraper Phase ───

def scrape_only(article: dict, job_id: str, sector: str, region: str, user_id: str) -> Optional[int]:
    if is_job_cancelled(job_id): return None
    try:
        url = article["url"]
        # Redirection and scraping are now handled in tasks.py via threaded browser
        resolved_url = article.get("resolved_url", url)
        raw_html = article.get("raw_html")

        if not raw_html:
            from scraper.orchestrator import _mark_article_processed
            _mark_article_processed(job_id)
            return None

        keywords = []
        with get_db_sync() as db:
            from db.database import WatchedBrand
            brand_obj = db.execute(select(WatchedBrand).where(WatchedBrand.name == sector).where(WatchedBrand.user_id == user_id)).scalar_one_or_none()
            if brand_obj and brand_obj.keywords: keywords = [k.strip() for k in brand_obj.keywords.split(",") if k.strip()]
        
        if not keywords:
            from scraper.config import SECTOR_KEYWORDS
            keywords.extend(SECTOR_KEYWORDS.get(sector.lower(), []))
            if not keywords and "brand_name" in article: keywords = [article["brand_name"]]

        pub_at_str = article.get("published_at")
        try: final_pub_at = datetime.fromisoformat(pub_at_str.replace('Z', '+00:00')) if isinstance(pub_at_str, str) else datetime.now()
        except: final_pub_at = datetime.now()

        body, author = None, None
        content = raw_html
        
        if any(x in content for x in ["403 Forbidden", "429 Too Many Requests", "Access Denied"]):
            # Note: marking unhealthiness is tricky without the proxy object here, 
            # but usually handled in browser.py or discovery phase.
            pass

        from scraper import parser
        body = parser.extract_body(content)
        author_data = parser.extract_author_v2(content)
        author = author_data.get("name")
        
        extra_meta = {"author_metadata": author_data}
        try:
            # Strategic HTML Snippeting for LLM Judge
            # Use limited slice to avoid backtracking on huge pages
            head_match = re.search(r"<head>.*?</head>", content[:15000], re.I | re.S)
            html_head = head_match.group(0) if head_match else ""
            
            # Take snippets from the start and end of body
            body_start_match = re.search(r"<body.*?>", content, re.I)
            body_start_idx = body_start_match.end() if body_start_match else 0
            html_top = content[body_start_idx:body_start_idx + 3000]
            html_bottom = content[-3000:]
            
            extra_meta["html_snippets"] = {
                "head": html_head[:2000],
                "top": html_top,
                "bottom": html_bottom
            }
        except Exception as e:
            logger.warning(f"Metadata snippeting failed for {url}: {e}")

        extracted_date = parser.extract_date(content)
        if extracted_date: final_pub_at = extracted_date

        if keywords:
            # Check relevance more robustly: title is high priority
            title_body = f"{article['title']} {body}"
            # Brand Tracker: If the brand name (sector) or ANY keyword is found, it's relevant.
            is_relevant = any(kw.lower() in title_body.lower() for kw in keywords)
            if not is_relevant:
                # If it's a brand tracker, also check the sector name itself just in case
                if sector.lower() in title_body.lower():
                    is_relevant = True
            
            if not is_relevant:
                body = None
        
        # 48h filter (Relaxed from 24h to avoid nuking articles discovered by Google but slightly older)
        now = datetime.now()
        if final_pub_at.tzinfo: now = now.astimezone(final_pub_at.tzinfo)
        date_invalid = (now - final_pub_at) > timedelta(hours=48)

        with get_db_sync() as db:
            if not body or date_invalid:
                from scraper.orchestrator import _mark_article_processed
                db.execute(delete(Article).where(Article.url == article["url"]))
                _mark_article_processed(job_id)
            else:
                val_dict = {
                    "title": article["title"],
                    "url": article["url"],
                    "resolved_url": resolved_url,
                    "full_body": body,
                    "author": author,
                    "agency": article.get("agency"),
                    "published_at": final_pub_at,
                    "sector": sector,
                    "region": region,
                    "scrape_job_id": job_id,
                    "user_id": user_id,
                    "extra_metadata": extra_meta
                }
                from sqlalchemy.dialects.postgresql import insert as pg_upsert
                stmt = pg_upsert(Article).values(**val_dict).on_conflict_do_update(
                    index_elements=[Article.url],
                    set_={
                        "full_body": val_dict["full_body"],
                        "author": val_dict["author"],
                        "agency": val_dict["agency"],
                        "extra_metadata": val_dict["extra_metadata"],
                        "published_at": val_dict["published_at"],
                        "scrape_job_id": val_dict["scrape_job_id"],
                        "resolved_url": val_dict["resolved_url"]
                    }
                ).returning(Article.id)
                db.execute(stmt)
                from scraper.orchestrator import _mark_article_processed
                _mark_article_processed(job_id)
            
            if body and not date_invalid:
                return article_id
    except Exception as e:
        log(f"Scrape fail: {e}")
    return None

def bulk_insert_placeholders(db, job_id, articles, sector, region, user_id):
    """
    Optimized batch ingestion using on_conflict_do_nothing.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_upsert
    
    # Chunker for batch scale
    BATCH_SIZE = 2000
    for i in range(0, len(articles), BATCH_SIZE):
        batch = articles[i:i + BATCH_SIZE]
        values = []
        for a in batch:
            try:
                values.append({
                    "title": a.get("title", "Article Discovery"), 
                    "url": a["url"], 
                    "published_at": datetime.fromisoformat(a["published_at"].replace('Z', '+00:00')) if isinstance(a["published_at"], str) else datetime.now(),
                    "sector": a.get("sector") or sector, 
                    "region": region, 
                    "scrape_job_id": job_id, 
                    "user_id": user_id, 
                    "agency": a.get("agency") or "Sitemap Discovery"
                })
            except: continue
        
        if values:
            db.execute(pg_upsert(Article).values(values).on_conflict_do_nothing(index_elements=[Article.url]))
            db.commit()

def run_scrape_job(job_id, sector, region, date_from, date_to, search_mode, user_id):
    log(f"Job {job_id} Start.")
    if isinstance(date_from, str): date_from = date.fromisoformat(date_from)
    if isinstance(date_to, str): date_to = date.fromisoformat(date_to)
    
    with get_db_sync() as db:
        db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(status='running', started_at=datetime.now()))
        update_phase_status(db, job_id, "Discovery", "running")
        
        keywords = []
        is_brand = False
        from db.database import WatchedBrand
        brand_obj = db.execute(select(WatchedBrand).where(WatchedBrand.name == sector).where(WatchedBrand.user_id == user_id)).scalar_one_or_none()
        if brand_obj:
            is_brand = True
            keywords = [k.strip() for k in brand_obj.keywords.split(",")] if brand_obj.keywords else [brand_obj.name]
        else:
            keywords = SECTOR_KEYWORDS.get(sector.lower(), [sector])

        geo = REGION_MAP.get(region.lower(), {"geo": "IN"})["geo"]
        all_discovered = []
        cumulative = set()
        
        # Parallel Discovery (Issue #4)
        from asgiref.sync import async_to_sync
        import asyncio
        
        dates = []
        curr = date_from
        while curr <= date_to:
            dates.append(curr)
            curr += timedelta(days=1)

        async def _parallel_discovery():
            tasks = []
            for d in dates:
                if is_job_cancelled(job_id): break
                tasks.append(asyncio.to_thread(discover_articles, keywords, d, geo, region, job_id, cumulative))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, list):
                    all_discovered.extend(res)
                elif isinstance(res, Exception):
                    logger.error(f"Discovery error in parallel batch: {res}")

        async_to_sync(_parallel_discovery)()
        
        db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(cumulative_found=len(cumulative)))
        update_phase_status(db, job_id, "Discovery", "completed")
        
        if not all_discovered:
            db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(status='completed', completed_at=datetime.now(), total_found=0))
            return {"job_id": job_id, "found": 0}

        bulk_insert_placeholders(db, job_id, all_discovered, sector, region, user_id)
        db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(total_found=len(all_discovered), current_phase="Scraping"))
        db.commit()

        from scraper.tasks import scrape_article_node
        for a in all_discovered:
            if is_job_cancelled(job_id): break
            scrape_article_node.delay(a, job_id, sector, region, user_id)
        
        return {"job_id": job_id, "found": len(all_discovered)}
