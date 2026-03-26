import asyncio
import logging
from playwright.async_api import async_playwright, Browser, BrowserContext

logger = logging.getLogger("BROWSER_POOL")

class BrowserPool:
    _instance = None
    _browser: Browser = None
    _playwright = None
    _use_count = 0
    _max_uses = 100 # Recycle browser after 100 requests to prevent memory leaks
    _last_active = 0
    _lock = asyncio.Lock()

    @classmethod
    async def get_browser(cls) -> Browser:
        async with cls._lock:
            # Lifecycle management: Launch if missing, disconnected, or exceeded use limit
            if cls._browser is None or not cls._browser.is_connected() or cls._use_count >= cls._max_uses:
                if cls._browser:
                    try:
                        await cls._browser.close()
                    except:
                        pass
                
                if cls._playwright is None:
                    cls._playwright = await async_playwright().start()
                
                logger.info(f"Launching shared Chromium instance (Previous Use Count: {cls._use_count})...")
                cls._browser = await cls._playwright.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
                )
                cls._use_count = 0
            
            cls._last_active = asyncio.get_event_loop().time()
            return cls._browser

    @classmethod
    async def fetch_content(cls, url: str, timeout: int = 30000) -> str:
        browser = await cls.get_browser()
        # Create a fresh context for each request to isolate cookies/cache
        context: BrowserContext = await browser.new_context()
        page = await context.new_page()
        
        try:
            cls._use_count += 1
            # Aggressive ad/media blocking to save bandwidth/CPU
            await page.route("**/*", lambda route: route.abort() 
                           if route.request.resource_type in ["image", "media", "font"] 
                           else route.continue_())
            
            logger.info(f"Pool fetching ({cls._use_count}/{cls._max_uses}): {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            await page.wait_for_timeout(1000) # Wait for potential redirects/JS
            return await page.content()
        except Exception as e:
            logger.error(f"Pool fetch error for {url}: {e}")
            raise
        finally:
            await context.close()
            cls._last_active = asyncio.get_event_loop().time()

    @classmethod
    async def close(cls):
        async with cls._lock:
            if cls._browser:
                await cls._browser.close()
                cls._browser = None
            if cls._playwright:
                await cls._playwright.stop()
                cls._playwright = None

# Shortcut functions
async def fetch_with_browser(url: str, timeout: int = 30000) -> str:
    return await BrowserPool.fetch_content(url, timeout)
