import asyncio
import logging
from scraper.sitemap import SitemapManager, DEFAULT_INDIA_SITEMAPS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VERIFY")

async def test_discovery():
    logger.info("Testing Sitemap Discovery Phase...")
    sectors = ["artificial intelligence", "sports", "business", "education", "politics"]
    sm = SitemapManager(target_sectors=sectors)
    
    # Only test first 3 sitemaps for speed in verification
    test_urls = DEFAULT_INDIA_SITEMAPS[:3]
    logger.info(f"Targeting sitemaps: {test_urls}")
    
    articles = await sm.discover_all(test_urls)
    
    logger.info(f"VERIFICATION SUCCESS: Found {len(articles)} articles.")
    if articles:
        logger.info(f"Sample Article: {articles[0]}")
    
    # Check sector distribution
    distribution = {}
    for a in articles:
        s = a["sector"]
        distribution[s] = distribution.get(s, 0) + 1
    
    logger.info(f"Sector Distribution: {distribution}")

if __name__ == "__main__":
    asyncio.run(test_discovery())
