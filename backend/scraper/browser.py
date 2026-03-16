import threading
import logging
import random
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
]

def scrape_url(url: str, timeout: int = 45000) -> str | None:
    """
    Runs Asynchronous Playwright in a new dedicated thread to avoid 
    Celery/gevent main loop conflicts.
    """
    import asyncio
    
    result = {"content": None, "error": None}

    async def _async_scrape():
        try:
            async with async_playwright() as p:
                ua = random.choice(USER_AGENTS)
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-software-rasterizer"]
                )
                try:
                    context = await browser.new_context(user_agent=ua)
                    page = await context.new_page()
                    
                    # BLOCK RESOURCES FOR SPEED
                    async def block_aggressively(route):
                        if route.request.resource_type in ["image", "media", "font", "stylesheet", "other"]:
                            await route.abort()
                        else:
                            await route.continue_()
                    
                    await page.route("**/*", block_aggressively)
                    
                    await page.set_extra_http_headers({
                        "Accept-Language": "en-US,en;q=0.9",
                    })

                    logger.info(f"Async Playwright scraper: Navigating to {url}")
                    response = await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
                    
                    if not response:
                        result["error"] = "No response"
                        return

                    if response.status >= 400:
                        result["error"] = f"HTTP {response.status}"
                        return

                    # Wait a bit for dynamic content
                    await page.wait_for_timeout(1000)
                    result["content"] = await page.content()
                    
                except Exception as e:
                    result["error"] = str(e)
                finally:
                    await browser.close()
        except Exception as e:
            result["error"] = f"Launch error: {str(e)}"

    def _run_in_thread():
        # Complete isolation layout
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_async_scrape())
        finally:
            loop.close()

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
