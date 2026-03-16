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
from typing import Optional, List, Dict, Any
from urllib.parse import quote_plus
from sqlalchemy import select, update, insert, text, delete
# from playwright.sync_api import sync_playwright
# from playwright_stealth import Stealth
from scraper.parser import extract_body, extract_author, extract_date, is_junk_body
from scraper.google_news import resolve_google_news_url_sync

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

# --- Proxy Management ---
class ProxyGuard:
    _unhealthy = {} 
    
    @classmethod
    def mark_unhealthy(cls, proxy_url: str, duration: int = 300):
        if not proxy_url: return
        cls._unhealthy[proxy_url] = time.time() + duration
        logger.info(f"PROXY-GUARD: Blacklisted {proxy_url[:30]}... for {duration}s")
        
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
    proxies = []
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for fname in ["Webshare 10 proxies.txt", "webshare_proxies.txt"]:
        fpath = os.path.join(base_dir, fname)
        if os.path.exists(fpath):
            with open(fpath, "r") as f:
                for line in f:
                    parts = line.strip().split(":")
                    if len(parts) == 4: proxies.append(f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}")
    
    user_base = os.getenv("WEBSHARE_PROXY_USER", "jxgqvosn")
    pw = os.getenv("WEBSHARE_PROXY_PASS", "symou02ck2bw")
    if user_base and pw:
        for i in range(1, 11): proxies.append(f"http://{user_base}-{i}:{pw}@p.webshare.io:80")
            
    proxies = list(dict.fromkeys(proxies))
    return proxies

def log(msg: str):
    logger.info(msg)

def random_ua() -> str:
    return random.choice(USER_AGENTS)

def update_phase_status(db, job_id, phase_name, status):
    try:
        res = db.execute(select(ScrapeJob.phase_stats).where(ScrapeJob.id == job_id))
        phase_stats_raw = res.scalar()
        current_stats = json.loads(phase_stats_raw) if phase_stats_raw else {}
        current_stats[phase_name] = {"status": status, "updated_at": datetime.now().isoformat()}
        db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(phase_stats=json.dumps(current_stats), current_phase=phase_name))
        db.commit()
    except Exception as e:
        log(f"Error updating phase status: {e}")

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
    proxy_pool = load_proxies() or [None]
    
    def fetch_rss(q, start_time, end_time, hl="en-IN", ceid="IN:en", attempt=0):
        if is_job_cancelled(job_id): return
        current_proxy = ProxyGuard.get_healthy_proxy(proxy_pool)
        
        # Use official tbs parameters for time filtering (C-X)
        # qdr:d = Past 24 hours (most reliable for recent news)
        # sbd:1 = Sort by Date (newest first)
        is_today = day >= date.today()
        if is_today:
            tbs = "qdr:d,sbd:1"
        else:
            # cdr:1 = Custom Date Range
            # cd_min/max: MM/DD/YYYY
            date_str = day.strftime("%m/%d/%Y")
            tbs = f"cdr:1,cd_min:{date_str},cd_max:{date_str},sbd:1"
        
        with httpx.Client(timeout=35, follow_redirects=True, proxy=current_proxy) as client:
            domain = REGION_MAP.get(geo, "google.com")
            rss_url = f"https://news.{domain}/rss/search?q={quote_plus(q)}&hl={hl}&gl=IN&ceid={ceid}&tbs={quote_plus(tbs)}"
            try:
                resp = client.get(rss_url, headers={"User-Agent": random_ua()})
                if resp.status_code in [407, 403, 429]:
                    ProxyGuard.mark_unhealthy(current_proxy)
                    if attempt < 3:
                        time.sleep(random.uniform(1, 3))
                        return fetch_rss(q, start_time, end_time, hl, ceid, attempt + 1)
                    raise ProxyFailureError(f"HTTP {resp.status_code}")
                if resp.status_code == 200:
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries:
                        link = entry.link
                        # Secondary safety: Google News RSS sometimes ignores tbs/cdr parameters
                        # and returns very old results (as seen in user screenshots).
                        # We verify the entry's timestamp if possible, but trust qdr:d more.
                        if link not in seen_urls and (cumulative is None or link not in cumulative):
                            parsed_date = None
                            if hasattr(entry, 'published_parsed'):
                                parsed_date = datetime.fromtimestamp(time.mktime(entry.published_parsed)).date()
                            
                            # If we have a date, strictly enforce it for historical scans.
                            # For 'today' (qdr:d), we allow it since rolling 24h is fine.
                            if not is_today and parsed_date and parsed_date != day:
                                continue
                                
                            pub_date_str = day.isoformat()
                            if hasattr(entry, 'published_parsed'):
                                try: pub_date_str = datetime(*entry.published_parsed[:6]).isoformat()
                                except: pass

                            articles.append({"title": entry.title, "url": link, "published_at": pub_date_str, "agency": entry.source.title if hasattr(entry, 'source') else "Google News"})
                            seen_urls.add(link)
                else: resp.raise_for_status()
            except Exception as exc:
                if attempt < 2: return fetch_rss(q, start_time, end_time, hl, ceid, attempt + 1)
                log(f"Discovery fail for '{q}': {exc}")

    search_languages = [{"code": "en-IN", "ceid": "IN:en"}]
    if region_name.lower() == "india":
        from scraper.config import INDIAN_LANGUAGES
        search_languages = INDIAN_LANGUAGES

    window_queries = [kw for kw in keywords]
    is_brand_tracker = False
    with get_db_sync() as db:
        job_res = db.execute(select(ScrapeJob.sector).where(ScrapeJob.id == job_id))
        sector_name = job_res.scalar()
        if sector_name:
            from db.database import WatchedBrand
            if db.execute(select(WatchedBrand).where(WatchedBrand.name == sector_name)).scalar_one_or_none():
                is_brand_tracker = True
    
    if not is_brand_tracker:
        for kw in keywords:
            for mod in random.sample(SEARCH_MODIFIERS, min(len(SEARCH_MODIFIERS), 5)): window_queries.append(f"{kw} {mod}")
    
    random.shuffle(window_queries)
    for lang in search_languages:
        if is_job_cancelled(job_id): break
        for q in window_queries:
            if is_job_cancelled(job_id): break
            fetch_rss(q, "00:00:00", "23:59:59", hl=lang['code'], ceid=lang['ceid'])
            time.sleep(random.uniform(0.1, 0.3))

    if cumulative is not None: cumulative.update(seen_urls)
    return articles

# ─── Scraper Phase ───

def scrape_only(article: dict, job_id: str, sector: str, region: str, user_id: str) -> Optional[int]:
    if is_job_cancelled(job_id): return None
    try:
        url = article["url"]
        # Redirection and scraping are now handled in tasks.py via threaded browser
        resolved_url = article.get("resolved_url", url)
        raw_html = article.get("raw_html")

        if not raw_html:
            # Fallback if somehow triggered without tasks.py wrapper
            with get_db_sync() as db: 
                db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(total_scraped=ScrapeJob.total_scraped + 1))
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

        body = trafilatura.extract(content)
        if not body or len(body) < 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, "lxml")
            for s in soup(["script", "style", "nav", "header", "footer"]): s.decompose()
            body = soup.get_text(separator="\n", strip=True)

        author = extract_author(content)
        extracted_date = extract_date(content)
        if extracted_date: final_pub_at = extracted_date

        if keywords and not verify_brand_relevance(f"{article['title']} {body}", keywords): body = None
        
        # 24h filter
        now = datetime.now()
        if final_pub_at.tzinfo: now = now.astimezone(final_pub_at.tzinfo)
        date_invalid = (now - final_pub_at) > timedelta(hours=24)

        with get_db_sync() as db:
            if not body or date_invalid:
                db.execute(delete(Article).where(Article.url == article["url"]))
                db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(total_scraped=ScrapeJob.total_scraped + 1))
            else:
                val_dict = {"title": article["title"], "url": article["url"], "full_body": body, "author": author, "agency": article.get("agency"), "published_at": final_pub_at, "sector": sector, "region": region, "scrape_job_id": job_id, "user_id": user_id}
                from sqlalchemy.dialects.postgresql import insert as pg_upsert
                stmt = pg_upsert(Article).values(**val_dict).on_conflict_do_update(index_elements=['url'], set_={"full_body": text("excluded.full_body"), "scrape_job_id": text("excluded.scrape_job_id")})
                db.execute(stmt)
                db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(total_scraped=ScrapeJob.total_scraped + 1))
            
            job = db.execute(select(ScrapeJob).where(ScrapeJob.id == job_id)).scalar_one_or_none()
            if job and job.total_scraped >= job.total_found:
                db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(status='completed', completed_at=datetime.now()))
            db.commit()
    except Exception as e:
        log(f"Scrape fail: {e}")
    return None

def bulk_insert_placeholders(db, job_id, articles, sector, region, user_id):
    for a in articles:
        try:
            val_dict = {"title": a["title"], "url": a["url"], "published_at": datetime.fromisoformat(a["published_at"]), "sector": sector, "region": region, "scrape_job_id": job_id, "user_id": user_id, "agency": a.get("agency")}
            from sqlalchemy.dialects.postgresql import insert as pg_upsert
            db.execute(pg_upsert(Article).values(**val_dict).on_conflict_do_nothing(index_elements=['url']))
        except: pass
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
        
        curr = date_from
        while curr <= date_to:
            if is_job_cancelled(job_id): break
            all_discovered.extend(discover_articles(keywords, curr, geo, region, job_id, cumulative))
            curr += timedelta(days=1)
        
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
