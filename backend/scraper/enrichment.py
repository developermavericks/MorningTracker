"""
Enrichment engine: Re-scrapes all articles that have bad/missing body text.
Handles:
  1. Google News redirect URLs (news.google.com/rss/articles/CBMi...)
  2. Blank / NULL bodies
  3. Junk content (< 80 words, Google News placeholder, JavaScript errors, paywalls)
"""

import asyncio
import os
import sys
import random
import json
import base64
import re
from datetime import datetime
from typing import Optional, List, Dict
import httpx
from bs4 import BeautifulSoup
from playwright_stealth import Stealth
from sqlalchemy import text, delete, update
from db.database import get_db, Article, ScrapeJob
from scraper.llm import summarize_with_groq, extract_metadata_with_ollama, verify_agency_with_ollama
from scraper.engine import get_browser_instance, get_browser_semaphore, shutdown_browser, logger
from scraper.parser import is_junk_body, extract_author as extract_author_from_html, extract_body as extract_body_from_html
from scraper.google_news import resolve_google_news_url


def log(msg: str):
    logger.info(msg)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
]

async def scrape_full_data(page, url: str) -> Dict[str, str]:
    """Scrape both text and HTML from a URL."""
    try:
        await page.route("**/*", lambda r: r.continue_() if r.request.resource_type in ("document", "xhr", "fetch") else r.abort())
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(1500)
        html = await page.content()
        return {"text": extract_body_from_html(html), "html": html}
    except Exception as e:
        log(f"Scrape error {url[:50]}: {e}")
        return {"text": "", "html": ""}

async def bypass_paywall(browser, url: str) -> Dict[str, str]:
    services = [
        ("archive.ph", lambda u: f"https://archive.ph/newest/{u}"),
        ("webcache", lambda u: f"https://webcache.googleusercontent.com/search?q=cache:{u}"),
    ]
    best = {"text": "", "html": ""}
    for name, make_url in services:
        target = make_url(url)
        context = None
        try:
            context = await browser.new_context(user_agent=random.choice(USER_AGENTS))
            page = await context.new_page()
            await Stealth().apply_stealth_async(page)
            await page.goto(target, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            html = await page.content()
            txt = extract_body_from_html(html)
            if len(txt) > len(best["text"]):
                best = {"text": txt, "html": html}
            if len(txt) > 600: break
        except Exception as e:
            log(f"Bypass {name} failed: {e}")
        finally:
            if context: await context.close()
    return best

async def fetch_with_paywall_bypass(browser, url: str) -> Dict[str, str]:
    """Try direct, then bypass."""
    # Direct
    context = await browser.new_context(user_agent=random.choice(USER_AGENTS))
    page = await context.new_page()
    await Stealth().apply_stealth_async(page)
    res = await scrape_full_data(page, url)
    await context.close()

    if not is_junk_body(res["text"]) and len(res["text"].split()) > 200:
        return res
    
    # Bypass
    log(f"Activating bypass for {url[:50]}")
    bypass_res = await bypass_paywall(browser, url)
    if len(bypass_res["text"]) > len(res["text"]):
        return bypass_res
    return res

async def run_enrichment(job_id: Optional[str] = None, batch_size: int = 1000):
    log(f"Starting enrichment. Batch size: {batch_size}")
    async with get_db() as db:
        res = await db.execute(text("""
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
    
    # Process in sub-batches
    for i in range(0, len(articles), 50):
        sub_batch = articles[i:i+50]
        
        async def enrich_one(item):
            nonlocal enriched, failed
            art_id = item["id"]
            raw_url = item["url"]
            
            async with get_browser_semaphore():
                active_browser = await get_browser_instance()
                try:
                    # 1. Resolve Redirect
                    real_url = await resolve_google_news_url(raw_url)
                    if not real_url: real_url = raw_url
                    
                    # 2. Fetch Data (Direct + Bypass)
                    data = await fetch_with_paywall_bypass(active_browser, real_url)
                    
                    if is_junk_body(data["text"]):
                        log(f"Enrichment: Article {art_id} flagged as junk, but keeping per high-discovery policy.")
                        # failed += 1
                        # return

                    # 3. Analyze
                    author = extract_author_from_html(data["html"])
                    ollama_meta = await extract_metadata_with_ollama(data["text"], url=real_url, context_agency=item.get("agency", ""))
                    
                    if not author and ollama_meta.get("author"): author = ollama_meta["author"]
                    agency = ollama_meta.get("agency") or item.get("agency")
                    
                    # 4. Summarize
                    final_body = ollama_meta.get("cleaned_body", data["text"])
                    summary = await summarize_with_groq(final_body)
                    
                    async with get_db() as db:
                        await db.execute(text("""
                            UPDATE articles 
                            SET full_body=:body, summary=:summary, author=:author, word_count=:words, url=:url, agency=:agency
                            WHERE id=:art_id
                        """), {
                            "body": final_body, "summary": summary, "author": author, 
                            "words": len(final_body.split()), "url": real_url, "agency": agency, "art_id": art_id
                        })
                        await db.commit()
                    
                    enriched += 1
                except Exception as e:
                    log(f"Enrichment error ID:{art_id}: {e}")
                    failed += 1

        tasks = [enrich_one(a) for a in sub_batch]
        await asyncio.gather(*tasks)
        
        # Sync Job Progress
        if job_id:
            async with get_db() as db:
                await db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(total_scraped=enriched+failed))
                await db.commit()

    log(f"Enrichment Done: {enriched} success, {failed} failed.")
    return {"enriched": enriched, "failed": failed}
