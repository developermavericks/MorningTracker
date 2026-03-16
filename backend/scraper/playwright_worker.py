import sys
import json
import asyncio
import random
from playwright.async_api import async_playwright

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
]

async def scrape(url, timeout):
    result = {"content": None, "error": None}
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
                
                async def block_aggressively(route):
                    if route.request.resource_type in ["image", "media", "font", "stylesheet", "other"]:
                        await route.abort()
                    else:
                        await route.continue_()
                
                await page.route("**/*", block_aggressively)
                await page.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})

                response = await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
                
                if not response:
                    result["error"] = "No response"
                elif response.status >= 400:
                    result["error"] = f"HTTP {response.status}"
                else:
                    await page.wait_for_timeout(1000)
                    for attempt in range(5):
                        try:
                            result["content"] = await page.content()
                            break  # Success!
                        except Exception as e:
                            if "navigating" in str(e).lower() and attempt < 4:
                                await page.wait_for_timeout(1500)  # Wait for redirect to finish
                            else:
                                raise e
            except Exception as e:
                result["error"] = str(e)
            finally:
                await browser.close()
    except Exception as e:
        result["error"] = f"Launch error: {str(e)}"
        
    print(json.dumps(result))

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(1)
    url = sys.argv[1]
    timeout = int(sys.argv[2])
    asyncio.run(scrape(url, timeout))
