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
# Removed resolve_google_news_url_sync as it's now internal to tasks.py Fast-Track

from db.database import get_db_sync, Article, ScrapeJob
from scraper.config import SECTOR_KEYWORDS, REGION_MAP, SEARCH_MODIFIERS, USER_AGENTS
from scraper.search_utils import verify_boolean_relevance, match_keyword

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
        return random.choice(healthy) if healthy else None

def load_proxies():
    # 1. Try DataImpulse proxy credentials from environment variables first
    di_proxy_url = os.getenv("DATAIMPULSE_PROXY_URL")
    if di_proxy_url:
        return [di_proxy_url]
    di_user = os.getenv("DATAIMPULSE_USER")
    di_pass = os.getenv("DATAIMPULSE_PASS")
    di_host = os.getenv("DATAIMPULSE_HOST")
    di_port = os.getenv("DATAIMPULSE_PORT")
    if di_user and di_pass and di_host and di_port:
        return [f"http://{di_user}:{di_pass}@{di_host}:{di_port}"]
        
    proxies = []
    # 2. Fallback to local Webshare proxy list files
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for fname in ["Webshare 10 proxies.txt", "webshare_proxies.txt"]:
        fpath = os.path.join(base_dir, fname)
        if os.path.exists(fpath):
            with open(fpath, "r") as f:
                for line in f:
                    parts = line.strip().split(":")
                    if len(parts) == 4: proxies.append(f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}")
    
    # 3. Fallback to legacy Webshare user credentials
    user_base = os.getenv("WEBSHARE_PROXY_USER", "jxgqvosn")
    pw = os.getenv("WEBSHARE_PROXY_PASS", "symou02ck2bw")
    if user_base and pw:
        for i in range(1, 11): proxies.append(f"http://{user_base}-{i}:{pw}@p.webshare.io:80")

    # Remove duplicates
    proxies = list(dict.fromkeys(proxies))
    
    if not proxies:
        logger.warning("No proxies loaded. Scraper will run without proxy protection.")
        
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

def normalize_url(url: str) -> str:
    """
    Strips tracking parameters and normalizes Google News redirects.
    Ensures URL collision detection works reliably.
    """
    if not url: return ""
    from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
    
    # 1. Strip common tracking params
    u = urlparse(url)
    query = dict(parse_qsl(u.query))
    tracking_params = [
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", 
        "utm_id", "utm_source_platform", "utm_marketing_tactic", "utm_creative_format",
        "ved", "usg", "oc", "hl", "gl", "ceid", "gclid", "fbclid", "msclkid", "dclid"
    ]
    keys_to_del = [k for k in query.keys() if k.lower().startswith("utm_") or k.lower() in tracking_params]
    for k in keys_to_del:
        del query[k]
    
    # Rebuild URL without tracking
    u = u._replace(query=urlencode(query))
    normalized = urlunparse(u)
    
    # 2. Lowercase domain for consistency
    u = urlparse(normalized)
    normalized = u._replace(netloc=u.netloc.lower()).geturl()
    
    return normalized

def verify_brand_relevance(text: str, keywords: List[str]) -> bool:
    """Verifies if the text matches the brand keywords using boolean logic."""
    if not text or not keywords: return True
    return verify_boolean_relevance(text, keywords)

GENERIC_TERMS = {
    "india", "ai", "artificial intelligence", "fintech", "fintechs", "banking", 
    "bank", "banks", "kyc", "upi", "credit", "card", "cards", "startups", "startup",
    "payments", "payment", "forex", "regulation", "regulations", "policy", "policies",
    "partnership", "partnerships", "growth", "ecosystem", "digital", "tools", "news", 
    "latest", "saas", "platform", "fraud", "prevention", "committee"
}

def is_generic_keyword(kw: str) -> bool:
    kw_clean = kw.lower().strip().replace('"', '').replace("'", "")
    if kw_clean in GENERIC_TERMS:
        return True
    words = re.findall(r'\b\w+\b', kw_clean)
    if words and all(w in GENERIC_TERMS for w in words):
        return True
    return False

def quote_keyword(kw: str) -> str:
    kw = kw.strip()
    if kw.startswith('"') and kw.endswith('"'):
        return kw
    return kw

# ─── Discovery Phase
def discover_articles(keywords: List[str], day: Optional[date], geo: str, region_name: str, job_id: str, cumulative: set = None, is_brand_track: bool = False, sector: str = "Unknown") -> List[dict]:
    articles = []
    seen_urls = set()
    proxy_pool = load_proxies() or []
    
    BRAND_TERMS = ["Scapia", "OneCard", "Niyo", "Fi Money", "Anil Goteti", "Uni Card", "Slice Card"]
    TOPIC_TERMS = [
        "credit card", "fintech", "banking", "AI", "travel rewards", 
        "co-branded", "payments", "forex", "RBI", "policy", "partnership"
    ]
    
    def fetch_rss(q, hl="en-IN", ceid="IN:en"):
        if is_job_cancelled(job_id): return
        
        domain = "google.com" # standard for news
        if day is None:
            rss_url = f"https://news.{domain}/rss/search?q={quote(q)}&hl={hl}&gl=IN&ceid={ceid}"
        elif day >= date.today():
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
            result_count = len(feed.entries)
            logger.info(f"QUERY RUN: q='{q}', count={result_count}, url='{rss_url}'")
            if result_count == 0:
                logger.warning(f"QUERY WARNING: Query '{q}' returned 0 results. RSS URL: {rss_url}")
                try:
                    from db.database import ZeroResultQuery
                    with get_db_sync() as db:
                        existing_q = db.execute(
                            select(ZeroResultQuery)
                            .where(ZeroResultQuery.query_string == q)
                            .where(ZeroResultQuery.sector == sector)
                        ).scalar_one_or_none()
                        if existing_q:
                            existing_q.count += 1
                            existing_q.logged_at = datetime.now()
                        else:
                            db.add(ZeroResultQuery(query_string=q, sector=sector))
                        db.commit()
                except Exception as db_err:
                    logger.error(f"Failed to log zero-result query to DB: {db_err}")
                
            for entry in feed.entries:
                link = entry.link
                if link not in seen_urls and (cumulative is None or link not in cumulative):
                    parsed_date = None
                    if hasattr(entry, 'published_parsed'):
                        parsed_date = datetime.fromtimestamp(time.mktime(entry.published_parsed)).date()
                    
                    if day is not None:
                        if day >= date.today():
                            if parsed_date and (day - parsed_date).days > 1:
                                continue
                        elif parsed_date and parsed_date != day:
                            continue
                        
                    pub_date_str = (day or date.today()).isoformat()
                    if hasattr(entry, 'published_parsed'):
                        try: pub_date_str = datetime(*entry.published_parsed[:6]).isoformat()
                        except: pass
                    
                    desc = entry.summary if hasattr(entry, 'summary') else (entry.description if hasattr(entry, 'description') else "")
                    articles.append({
                        "title": entry.title, 
                        "url": link, 
                        "published_at": pub_date_str, 
                        "agency": entry.source.title if hasattr(entry, 'source') else "Google News",
                        "description": desc
                    })
                    seen_urls.add(link)
        except Exception as exc:
            logger.error(f"Discovery fail for '{q}': {exc}")

    # Build queries programmatically as smaller, validated chunks
    window_queries = []
    cleaned_kws = list(dict.fromkeys([kw.strip() for kw in keywords if kw.strip()]))
    
    if is_brand_track:
        # Core Tier: Direct brand keywords (never drop or AND them with anything)
        for kw in cleaned_kws:
            q = quote_keyword(kw)
            if len(q) <= 256:
                window_queries.append(q)
        
        # Trend Tier: Brand terms ORed and then ANDed with topic terms
        brand_or_terms = " OR ".join([quote_keyword(b) for b in cleaned_kws])
        comp_terms = [b for b in BRAND_TERMS if b.lower() not in [k.lower() for k in cleaned_kws]]
        
        if comp_terms:
            brand_or_terms = f"({brand_or_terms}) OR " + " OR ".join([quote_keyword(c) for c in comp_terms])
            
        for topic in TOPIC_TERMS:
            q = f"({brand_or_terms}) AND \"{topic}\""
            if len(q) <= 256:
                window_queries.append(q)
            else:
                # Truncate to core brand terms if too long
                truncated_brand_or = " OR ".join([quote_keyword(b) for b in cleaned_kws])
                q_alt = f"({truncated_brand_or}) AND \"{topic}\""
                if len(q_alt) <= 256:
                    window_queries.append(q_alt)
    else:
        # Sector tracking (non-brand)
        tier1_kws = []
        tier2_kws = []
        for kw in cleaned_kws:
            if is_generic_keyword(kw):
                tier2_kws.append(kw)
            else:
                tier1_kws.append(kw)
        
        # Core Tier: Specific Tier 1 keywords searched directly
        for kw in tier1_kws:
            q = quote_keyword(kw)
            if len(q) <= 256:
                window_queries.append(q)
                
        # Intersect Tier 1 chunk OR-groups with Tier 2 chunk OR-groups
        chunk_size_t1 = 5
        chunk_size_t2 = 5
        
        if tier1_kws:
            for i in range(0, len(tier1_kws), chunk_size_t1):
                chunk_t1 = tier1_kws[i:i+chunk_size_t1]
                chunk_t1_str = " OR ".join([quote_keyword(k) for k in chunk_t1])
                
                # 1. Intersect with Tier 2 (generic terms)
                if tier2_kws:
                    for j in range(0, len(tier2_kws), chunk_size_t2):
                        chunk_t2 = tier2_kws[j:j+chunk_size_t2]
                        chunk_t2_str = " OR ".join([quote_keyword(k) for k in chunk_t2])
                        q = f"({chunk_t1_str}) AND ({chunk_t2_str})"
                        if len(q) <= 256:
                            window_queries.append(q)
                
                # 2. Intersect with generic modifiers
                for mod in ["news", "latest", "regulation", "partnership"]:
                    q = f"({chunk_t1_str}) AND {mod}"
                    if len(q) <= 256:
                        window_queries.append(q)
        else:
            # If no Tier 1 keywords exist, fallback to searching generic terms with modifiers
            for i in range(0, len(tier2_kws), chunk_size_t2):
                chunk_t2 = tier2_kws[i:i+chunk_size_t2]
                chunk_t2_str = " OR ".join([quote_keyword(k) for k in chunk_t2])
                for mod in ["news", "latest", "regulation", "partnership"]:
                    q = f"({chunk_t2_str}) AND {mod}"
                    if len(q) <= 256:
                        window_queries.append(q)

        # Create a targeted query chunk for Category A domains to ensure they are fetched
        cat_a_domains_query = "site:reuters.com OR site:bloomberg.com OR site:economictimes.indiatimes.com OR site:livemint.com OR site:timesofindia.indiatimes.com OR site:hindustantimes.com OR site:indianexpress.com"
        
        # Add a focused query for generic/tier 2 keywords restricted to Category A sources
        if tier2_kws:
            for i in range(0, len(tier2_kws), chunk_size_t2):
                chunk_t2 = tier2_kws[i:i+chunk_size_t2]
                chunk_t2_str = " OR ".join([quote_keyword(k) for k in chunk_t2])
                q = f"({chunk_t2_str}) AND ({cat_a_domains_query})"
                if len(q) <= 256:
                    window_queries.append(q)

    # Deduplicate queries to avoid double fetches
    window_queries = list(dict.fromkeys(window_queries))
    random.shuffle(window_queries)
    
    search_languages = [{"code": "en-IN", "ceid": "IN:en"}]
    
    # Discovery Acceleration: Parallelize with a larger pool
    discovery_pool = Pool(10)
    for lang in search_languages:
        if is_job_cancelled(job_id): break
        for q in window_queries:
            if is_job_cancelled(job_id): break
            discovery_pool.spawn(fetch_rss, q, hl=lang['code'], ceid=lang['ceid'])
    
    discovery_pool.join()

    if cumulative is not None: cumulative.update(seen_urls)
    return articles

def discover_direct_feeds(keywords: List[str], day: Optional[date], job_id: str, cumulative: set = None, sector: str = "Unknown") -> List[dict]:
    articles = []
    seen_urls = set()
    from db.database import get_db_sync
    
    # 1. Fetch active direct feeds from DB
    feeds = []
    try:
        with get_db_sync() as db:
            res = db.execute(text("SELECT feed_url, publication_name FROM direct_feeds WHERE is_active = true"))
            feeds = [{"url": r[0], "name": r[1]} for r in res.all()]
    except Exception as e:
        logger.error(f"Failed to fetch direct feeds from database: {e}")
        return []
        
    if not feeds:
        return []
        
    proxy_pool = load_proxies() or []
    
    def fetch_direct_feed(feed_info):
        feed_url = feed_info["url"]
        pub_name = feed_info["name"]
        
        try:
            proxy = ProxyGuard.get_healthy_proxy(proxy_pool)
            xml_content = NetworkHandler.get_google_rss(feed_url, proxy=proxy)
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
                    
                    if day is not None:
                        if day >= date.today():
                            if parsed_date and (day - parsed_date).days > 1:
                                continue
                        elif parsed_date and parsed_date != day:
                            continue
                            
                    pub_date_str = (day or date.today()).isoformat()
                    if hasattr(entry, 'published_parsed'):
                        try: pub_date_str = datetime(*entry.published_parsed[:6]).isoformat()
                        except: pass
                        
                    desc = entry.summary if hasattr(entry, 'summary') else (entry.description if hasattr(entry, 'description') else "")
                    
                    # Run keyword match
                    title = entry.title
                    title_desc = f"{title} {desc}"
                    is_relevant = verify_boolean_relevance(title_desc, keywords)
                    if not is_relevant and sector.lower() in title_desc.lower():
                        is_relevant = True
                        
                    if is_relevant:
                        articles.append({
                            "title": title,
                            "url": link,
                            "published_at": pub_date_str,
                            "agency": pub_name,
                            "description": desc
                        })
                        seen_urls.add(link)
        except Exception as exc:
            logger.error(f"Direct feed discovery fail for '{pub_name}' ({feed_url}): {exc}")

    # Use parallel Pool to scrape direct feeds concurrently
    discovery_pool = Pool(min(len(feeds), 5))
    for f_info in feeds:
        if is_job_cancelled(job_id): break
        discovery_pool.spawn(fetch_direct_feed, f_info)
        
    discovery_pool.join()
    
    if cumulative is not None: cumulative.update(seen_urls)
    logger.info(f"Direct RSS feeds discovery found {len(articles)} relevant articles.")
    return articles

# ─── Scraper Phase ───

def scrape_only(article: dict, job_id: str, sector: str, region: str, user_id: str) -> Optional[int]:
    if is_job_cancelled(job_id): return None
    try:
        url = article["url"]
        # Normalize original URL for lookups/duplicates
        normalized_url = normalize_url(url)
        
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
            # Use .first() as per user request to handle legacy duplicates gracefully
            brand_obj = db.execute(select(WatchedBrand).where(WatchedBrand.name == sector).where(WatchedBrand.user_id == user_id)).first()
            if brand_obj:
                brand_obj = brand_obj[0] # SQLAlchemy returns a Row object
                if brand_obj.keywords: keywords = [k.strip() for k in brand_obj.keywords.split(",") if k.strip()]
        
        if not keywords:
            from scraper.config import SECTOR_KEYWORDS
            keywords.extend(SECTOR_KEYWORDS.get(sector.lower(), []))
            if not keywords and "brand_name" in article: keywords = [article["brand_name"]]

        pub_at_str = article.get("published_at")
        try: final_pub_at = datetime.fromisoformat(pub_at_str.replace('Z', '+00:00')) if isinstance(pub_at_str, str) else datetime.now()
        except: final_pub_at = datetime.now()

        body, author = None, None
        content = raw_html
        
        body = extract_body(content)

        author_data = extract_author_v2(content)
        author = author_data.get("name")
        
        extra_meta = {"author_metadata": author_data}
        try:
            # Take snippets from the start and end of body
            body_start_match = re.search(r"<body.*?>", content[:15000], re.I)
            body_start_idx = body_start_match.end() if body_start_match else 0
            html_top = content[body_start_idx:body_start_idx + 3000]
            html_bottom = content[-3000:]
            
            extra_meta["html_snippets"] = {
                "top": html_top,
                "bottom": html_bottom
            }
        except Exception as e:
            logger.warning(f"Metadata snippeting failed for {url}: {e}")

        extracted_date = extract_date(content)
        if extracted_date: final_pub_at = extracted_date

        if keywords:
            title_body = f"{article['title']} {body}"
            is_relevant = verify_boolean_relevance(title_body, keywords)
            
            # Fallback: if no keywords match but the sector name is mentioned, consider it relevant
            # This handles cases where modifiers might be too strict
            if not is_relevant and match_keyword(title_body, sector):
                is_relevant = True
            
            if not is_relevant:
                body = None
        
        now = datetime.now()
        if final_pub_at.tzinfo: now = now.astimezone(final_pub_at.tzinfo)
        # Increase threshold to 96h (4 days) to support 3-day lookback window
        date_invalid = (now - final_pub_at) > timedelta(hours=96)

        with get_db_sync() as db:
            if not body or date_invalid:
                db.execute(delete(Article).where(Article.url == normalized_url))
                db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(total_scraped=ScrapeJob.total_scraped + 1))
            else:
                val_dict = {
                    "title": article["title"],
                    "url": normalized_url,
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
                
                # Portable Upsert: Check if exists for SQLite, use ON CONFLICT for PG
                if "postgresql" in str(db.bind.url):
                    from sqlalchemy.dialects.postgresql import insert as pg_upsert
                    stmt = pg_upsert(Article).values(**val_dict).on_conflict_do_update(
                        index_elements=[Article.url, Article.user_id],
                        set_={
                            "full_body": val_dict["full_body"],
                            "author": val_dict["author"],
                            "agency": val_dict["agency"],
                            "extra_metadata": val_dict["extra_metadata"],
                            "published_at": val_dict["published_at"],
                            "resolved_url": val_dict["resolved_url"],
                            "scrape_job_id": val_dict["scrape_job_id"]
                        }
                    ).returning(Article.id)
                    res = db.execute(stmt)
                    article_id = res.scalar()
                else:
                    # SQLite-safe upsert
                    existing = db.execute(select(Article).where(Article.url == normalized_url).where(Article.user_id == user_id)).first()
                    if existing:
                        existing_obj = existing[0]
                        for k, v in val_dict.items():
                            setattr(existing_obj, k, v)
                        article_id = existing_obj.id
                    else:
                        res = db.execute(insert(Article).values(**val_dict).returning(Article.id))
                        article_id = res.scalar()

                db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(total_scraped=ScrapeJob.total_scraped + 1))
            
            job = db.execute(select(ScrapeJob).where(ScrapeJob.id == job_id)).first()
            if job:
                job_obj = job[0]
                if job_obj.total_scraped >= job_obj.total_found:
                    db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(status='completed', completed_at=datetime.now()))
            db.commit()
            
            if body and not date_invalid:
                return article_id
    except Exception as e:
        log(f"Scrape fail: {e}")
    return None

def bulk_insert_placeholders(db, job_id, articles, sector, region, user_id):
    for a in articles:
        try:
            norm_url = normalize_url(a["url"])
            final_sector = a.get("brand_name", sector)
            val_dict = {"title": a["title"], "url": norm_url, "published_at": datetime.fromisoformat(a["published_at"]), "sector": final_sector, "region": region, "scrape_job_id": job_id, "user_id": user_id, "agency": a.get("agency")}
            
            # Portable Upsert Hack: Check if exists first for SQLite compliance 
            # while maintaining speed for placeholder phase.
            exists = db.execute(select(Article.id).where(Article.url == norm_url).where(Article.user_id == user_id)).first()
            if not exists:
                db.execute(insert(Article).values(**val_dict))
        except Exception as e:
            logger.debug(f"Placeholder insert skip for {a['url']}: {e}")
    db.commit()

def run_scrape_job(job_id, sector, region, date_from, date_to, search_mode, user_id):
    log(f"Job {job_id} Start.")
    if isinstance(date_from, str): date_from = date.fromisoformat(date_from)
    if isinstance(date_to, str): date_to = date.fromisoformat(date_to)
    
    with get_db_sync() as db:
        db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(status='running', started_at=datetime.now()))
        update_phase_status(db, job_id, "Discovery", "running")
        
        all_discovered = []
        cumulative = set()
        geo = REGION_MAP.get(region.lower(), {"geo": "IN"})["geo"]
        from db.database import WatchedBrand

        if sector == "brand_tracker":
            # Global Brand Scrape: iterate over all brands for this user
            res = db.execute(select(WatchedBrand).where(WatchedBrand.user_id == user_id))
            user_brands = res.scalars().all()
            if not user_brands:
                log(f"No brands found for user {user_id}. Job {job_id} terminating.")
                db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(status='completed', completed_at=datetime.now(), total_found=0))
                return {"job_id": job_id, "found": 0}

            for brand_obj in user_brands:
                if is_job_cancelled(job_id): break
                keywords = [k.strip() for k in brand_obj.keywords.split(",")] if brand_obj.keywords else [brand_obj.name]
                
                curr = date_from
                while curr <= date_to:
                    if is_job_cancelled(job_id): break
                    found = discover_articles(keywords, curr, geo, region, job_id, cumulative, is_brand_track=True, sector=brand_obj.name)
                    for f in found:
                        f["brand_name"] = brand_obj.name # Tag for later phases
                    all_discovered.extend(found)
                    
                    # Direct feed discovery
                    found_direct = discover_direct_feeds(keywords, curr, job_id, cumulative, sector=brand_obj.name)
                    for f in found_direct:
                        f["brand_name"] = brand_obj.name
                    all_discovered.extend(found_direct)
                    
                    curr += timedelta(days=1)
        else:
            # Single Sector/Brand Scrape
            keywords = []
            brand_obj = db.execute(select(WatchedBrand).where(WatchedBrand.name == sector).where(WatchedBrand.user_id == user_id)).scalar_one_or_none()
            if brand_obj:
                keywords = [k.strip() for k in brand_obj.keywords.split(",")] if brand_obj.keywords else [brand_obj.name]
            else:
                keywords = SECTOR_KEYWORDS.get(sector.lower(), [sector])

            is_bt = (brand_obj is not None)
            curr = date_from
            while curr <= date_to:
                if is_job_cancelled(job_id): break
                all_discovered.extend(discover_articles(keywords, curr, geo, region, job_id, cumulative, is_brand_track=is_bt, sector=sector))
                all_discovered.extend(discover_direct_feeds(keywords, curr, job_id, cumulative, sector=sector))
                curr += timedelta(days=1)
        
        db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(cumulative_found=len(cumulative)))
        update_phase_status(db, job_id, "Discovery", "completed")
        
        if not all_discovered:
            db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(status='completed', completed_at=datetime.now(), total_found=0))
            return {"job_id": job_id, "found": 0}

        bulk_insert_placeholders(db, job_id, all_discovered, sector, region, user_id)
        from db.database import JobFunnelLog
        db.execute(insert(JobFunnelLog).values(job_id=job_id, rss_discovered=len(all_discovered)))
        db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(total_found=len(all_discovered), current_phase="Scraping"))
        db.commit()

        from scraper.tasks import scrape_article_node
        for a in all_discovered:
            if is_job_cancelled(job_id): break
            # Crucial: pass the actual brand name as sector if it's a global job
            final_sector = a.get("brand_name", sector)
            scrape_article_node.delay(a, job_id, final_sector, region, user_id)
        
        return {"job_id": job_id, "found": len(all_discovered)}


async def test_browser_launch():
    """Verify Playwright can launch chromium successfully."""
    from playwright.async_api import async_playwright
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            )
            await browser.close()
            return {"status": "ok", "message": "Playwright launched browser successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

