import time
import random
import logging
import httpx
import hashlib
from typing import Optional
from gevent.lock import BoundedSemaphore
from scraper.llm import get_redis_sync

logger = logging.getLogger(__name__)

# Concurrency Control: Cap active Google News requests to 5
google_semaphore = BoundedSemaphore(5)

class NetworkHandler:
    @staticmethod
    def get_google_rss(url: str, proxy: Optional[str] = None, use_cache: bool = True) -> Optional[str]:
        """
        Centralized Google News RSS fetcher with:
        - Concurrency capping (Semaphore)
        - Cache (Redis)
        - Random delays
        - 503 Detection and Exponential Backoff
        """
        redis = get_redis_sync()
        cache_key = f"nexus:rss_cache:{hashlib.md5(url.encode()).hexdigest()}"
        
        if use_cache:
            cached = redis.get(cache_key)
            if cached:
                # logger.info(f"Cache HIT for {url[:50]}...")
                return cached if isinstance(cached, str) else cached.decode('utf-8')

        # Global Throttle Check: If we see too many 503s globally, cool down
        throttle_count = int(redis.get("nexus:global_503_count") or 0)
        if throttle_count > 5:
            # logger.warning("Global throttle active. Cooling down for 60s...")
            time.sleep(60)
            redis.delete("nexus:global_503_count")

        with google_semaphore:
            # Per-request random delay (Politeness)
            time.sleep(random.uniform(1.0, 3.0))
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            }
            
            client_args = {"timeout": 30, "follow_redirects": True}
            if proxy:
                client_args["proxy"] = proxy

            attempts = 3
            backoff = 4
            
            for i in range(attempts):
                try:
                    with httpx.Client(**client_args) as client:
                        resp = client.get(url, headers=headers)
                        
                        if resp.status_code == 200:
                            content = resp.text
                            # Cache successful results for 1 hour
                            redis.setex(cache_key, 3600, content)
                            return content
                        
                        if resp.status_code == 503:
                            logger.warning(f"Google 503 detected for {url[:50]}... Attempt {i+1}/{attempts}")
                            redis.incrby("nexus:global_503_count", 1)
                            redis.expire("nexus:global_503_count", 60)
                            time.sleep(backoff)
                            backoff *= 2 # Exponential backoff
                            continue
                            
                        resp.raise_for_status()
                except Exception as e:
                    if i == attempts - 1:
                        logger.error(f"Failed to fetch Google RSS after {attempts} attempts: {e}")
                    time.sleep(backoff)
                    backoff *= 2
                    
        return None
