import threading
import logging
import random
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
]

def scrape_url(url: str, timeout: int = 45000) -> str | None:
    """
    Runs Synchronous Playwright in a brand new thread.
    This avoids event loop conflicts with gevent/asyncio.
    """
    result = {"content": None, "error": None}

    def _run_in_thread():
        import asyncio
        import nest_asyncio
        
        # Patch the event loop so playwright's internal asyncio usage 
        # doesn't collide with the existing active loop in this thread
        nest_asyncio.apply()
        
        try:
            with sync_playwright() as p:
                ua = random.choice(USER_AGENTS)
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-software-rasterizer"]
                )
                try:
                    context = browser.new_context(user_agent=ua)
                    page = context.new_page()
                    
                    # BLOCK RESOURCES FOR SPEED (Sync API)
                    def block_aggressively(route):
                        if route.request.resource_type in ["image", "media", "font", "stylesheet", "other"]:
                            route.abort()
                        else:
                            route.continue_()
                    
                    page.route("**/*", block_aggressively)
                    
                    page.set_extra_http_headers({
                        "Accept-Language": "en-US,en;q=0.9",
                    })

                    logger.info(f"Threaded sync scraper: Navigating to {url}")
                    response = page.goto(url, timeout=timeout, wait_until="domcontentloaded")
                    
                    if not response:
                        result["error"] = "No response"
                        return

                    if response.status >= 400:
                        result["error"] = f"HTTP {response.status}"
                        return

                    # Wait a bit for dynamic content
                    page.wait_for_timeout(1000)
                    result["content"] = page.content()
                    
                except Exception as e:
                    result["error"] = str(e)
                finally:
                    browser.close()
        except Exception as e:
            result["error"] = f"Launch error: {str(e)}"

    thread = threading.Thread(target=_run_in_thread, daemon=True)
    thread.start()
    
    # Wait for the thread to finish
    thread.join(timeout=(timeout / 1000) + 15)

    if thread.is_alive():
        logger.error(f"Scraper thread timed out for {url}")
        return None

    if result["error"]:
        logger.error(f"Scraper error for {url}: {result['error']}")
        return None

    return result["content"]
