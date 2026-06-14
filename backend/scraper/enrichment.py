"""
Enrichment engine: Synchronous version for Gevent.
"""

import time
import os
import sys
import random
import json
import re
from datetime import datetime
from typing import Optional, List, Dict
import httpx
from bs4 import BeautifulSoup
from playwright_stealth import Stealth
from playwright.sync_api import sync_playwright
from sqlalchemy import text, delete, update
from db.database import get_db_sync, Article, ScrapeJob
from scraper.llm import summarize_with_groq_sync, extract_metadata_with_groq_sync
from scraper.engine import ProxyGuard, load_proxies, logger, random_ua
from scraper.parser import is_junk_body, extract_author_v2, extract_body as extract_body_from_html
from scraper.google_news import resolve_google_news_url_sync

def log(msg: str):
    logger.info(msg)

def scrape_full_data_sync(page, url: str) -> Dict[str, str]:
    try:
        page.route("**/*", lambda r: r.continue_() if r.request.resource_type in ("document", "xhr", "fetch") else r.abort())
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(1500)
        html = page.content()
        return {"text": extract_body_from_html(html), "html": html}
    except Exception as e:
        log(f"Scrape error {url[:50]}: {e}")
        return {"text": "", "html": ""}

def run_enrichment_sync(job_id: Optional[str] = None, batch_size: int = 1000):
    log(f"Starting enrichment. Batch size: {batch_size}")
    with get_db_sync() as db:
        res = db.execute(text("""
            SELECT id, url, title, agency FROM articles
            WHERE full_body IS NULL OR length(full_body) < 150 OR lower(full_body) LIKE '%javascript%'
            ORDER BY id DESC LIMIT :batch_size
        """), {"batch_size": batch_size})
        articles = res.mappings().all()
        
        if not articles:
            log("No articles to enrich.")
            return {"enriched":0, "failed":0}

        enriched = 0
        failed = 0
        
        proxies = load_proxies()
        with sync_playwright() as p:
            for item in articles:
                art_id = item["id"]
                raw_url = item["url"]
                
                proxy_args = {"proxy": {"server": ProxyGuard.get_healthy_proxy(proxies)}} if proxies else {}
                browser = p.chromium.launch(headless=True, **proxy_args)
                try:
                    context = browser.new_context(user_agent=random_ua())
                    page = context.new_page()
                    Stealth().apply_stealth_sync(page)
                    
                    # 1. Resolve Redirect
                    real_url = resolve_google_news_url_sync(raw_url) or raw_url
                    
                    # 2. Fetch Data
                    data = scrape_full_data_sync(page, real_url)
                    
                    if is_junk_body(data["text"]):
                        log(f"Enrichment: Article {art_id} flagged as junk.")

                    # 3. Analyze
                    author_data = extract_author_v2(data["html"])
                    html_top, html_bottom = "", ""
                    try:
                        body_start_match = re.search(r"<body.*?>", data["html"][:15000], re.I)
                        body_start_idx = body_start_match.end() if body_start_match else 0
                        html_top = data["html"][body_start_idx:body_start_idx + 3000]
                        html_bottom = data["html"][-3000:]
                    except:
                        pass

                    groq_meta = extract_metadata_with_groq_sync(
                        data["text"], 
                        url=real_url, 
                        context_agency=item.get("agency", ""),
                        author_metadata=author_data,
                        html_snippets={"top": html_top, "bottom": html_bottom}
                    )
                    author = groq_meta.get("author")
                    if groq_meta.get("handle"):
                        author = f"{author} (@{groq_meta['handle']})" if author else f"@{groq_meta['handle']}"
                    
                    agency = groq_meta.get("agency") or item.get("agency")
                    
                    # 4. Summarize
                    final_body = groq_meta.get("cleaned_body", data["text"])
                    summary = summarize_with_groq_sync(final_body)
                    
                    db.execute(text("""
                        UPDATE articles 
                        SET full_body=:body, summary=:summary, author=:author, word_count=:words, url=:url, agency=:agency
                        WHERE id=:art_id
                    """), {
                        "body": final_body, "summary": summary, "author": author, 
                        "words": len(final_body.split()), "url": real_url, "agency": agency, "art_id": art_id
                    })
                    db.commit()
                    enriched += 1
                except Exception as e:
                    log(f"Enrichment error ID:{art_id}: {e}")
                    failed += 1
                finally:
                    browser.close()

                if job_id:
                    db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(total_scraped=enriched+failed))
                    db.commit()

    log(f"Enrichment Done: {enriched} success, {failed} failed.")
    return {"enriched": enriched, "failed": failed}
