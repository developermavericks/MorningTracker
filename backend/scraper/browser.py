import logging
import json
import asyncio
from asgiref.sync import async_to_sync
from scraper.browser_pool import fetch_with_browser

logger = logging.getLogger(__name__)

# Synchronous wrapper for gevent-based workers
fetch_sync = async_to_sync(fetch_with_browser)

def scrape_url(url: str, timeout: int = 45000) -> str | None:
    """
    Fetches HTML using the shared browser pool.
    Replaces the old subprocess-based fallback for better performance.
    """
    logger.info(f"Pool-based scraper: Navigating to {url}")
    try:
        content = fetch_sync(url, timeout=timeout)
        if not content:
            logger.error(f"Scraper returned empty output for {url}")
            return None
        return content
            
    except Exception as e:
        logger.error(f"Scraper pool error for {url}: {str(e)}")
        return None
