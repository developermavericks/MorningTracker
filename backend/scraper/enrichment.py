import asyncio
import logging
import time
from typing import Optional, List, Dict, Any
from asgiref.sync import async_to_sync
from sqlalchemy import text, update

from db.database import get_db_sync, Article, ScrapeJob
from scraper.llm import summarize_with_groq_sync, extract_metadata_with_ollama_sync
from scraper.engine import logger, random_ua
from scraper.parser import is_junk_body, extract_author as extract_author_from_html, extract_body as extract_body_from_html
from scraper.google_news import resolve_google_news_url_sync
from scraper.browser_pool import fetch_with_browser

def log(msg: str):
    logger.info(msg)

async def _enrich_one_article(item: Dict[str, Any], db):
    art_id = item["id"]
    raw_url = item["url"]
    agency_context = item.get("agency", "")
    
    try:
        # 1. Resolve Redirect
        real_url = resolve_google_news_url_sync(raw_url) or raw_url
        
        # 2. Fetch Data using Pool
        html = await fetch_with_browser(real_url)
        if not html:
            return False

        data = {
            "text": extract_body_from_html(html),
            "html": html
        }
        
        if is_junk_body(data["text"]):
            log(f"Enrichment: Article {art_id} flagged as junk.")

        # 3. Analyze (LLM calls are still serial here, but the fetch is concurrent across articles)
        ollama_meta = extract_metadata_with_ollama_sync(data["text"], url=real_url, context_agency=agency_context)
        author = extract_author_from_html(data["html"]) or ollama_meta.get("author")
        agency = ollama_meta.get("agency") or agency_context
        
        # 4. Summarize
        final_body = ollama_meta.get("cleaned_body", data["text"])
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
        return True
    except Exception as e:
        log(f"Enrichment error ID:{art_id}: {e}")
        return False

async def run_enrichment_async(job_id: Optional[str] = None, batch_size: int = 1000):
    log(f"Starting async enrichment. Batch size: {batch_size}")
    with get_db_sync() as db:
        res = db.execute(text("""
            SELECT id, url, title, agency FROM articles
            WHERE full_body IS NULL OR length(full_body) < 150 OR lower(full_body) LIKE '%javascript%'
            ORDER BY id DESC LIMIT :batch_size
        """), {"batch_size": batch_size})
        articles = res.mappings().all()
        
        if not articles:
            log("No articles to enrich.")
            return {"enriched": 0, "failed": 0}

        # Run all enrichments concurrently
        tasks = [_enrich_one_article(dict(a), db) for a in articles]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        enriched = sum(1 for r in results if r is True)
        failed = sum(1 for r in results if r is False or isinstance(r, Exception))
        
        if job_id:
            db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(total_scraped=enriched + failed))
            db.commit()

    log(f"Enrichment Done: {enriched} success, {failed} failed.")
    return {"enriched": enriched, "failed": failed}

# Synchronous wrapper for existing callers (gevent)
def run_enrichment_sync(job_id: Optional[str] = None, batch_size: int = 1000):
    return async_to_sync(run_enrichment_async)(job_id, batch_size)
