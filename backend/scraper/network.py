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
                "User-Agent": random.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.6533.120 Safari/537.36",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.6533.120 Safari/537.36",
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.6478.229 Safari/537.36",
                ]),
                "Accept-Language": "en-US,en;q=0.9",
            }
            
            client_args = {"timeout": 30, "follow_redirects": True}
            if proxy:
                client_args["proxy"] = proxy

            attempts = 3

            def _try_fetch(args: dict) -> Optional[str]:
                """Fetch with retries. Returns content on 200, None on permanent failure."""
                backoff = 4
                for i in range(attempts):
                    try:
                        with httpx.Client(**args) as client:
                            resp = client.get(url, headers=headers)

                            if resp.status_code == 200:
                                content = resp.text
                                redis.setex(cache_key, 3600, content)
                                return content

                            # 407 = proxy quota exhausted or auth failure.
                            # Retrying is pointless — return immediately so caller
                            # can blacklist the proxy and fall back to direct.
                            if resp.status_code == 407:
                                logger.warning(
                                    f"Proxy 407 ({resp.text[:80].strip()}) for {url[:50]}. "
                                    "Skipping retries — quota exhausted."
                                )
                                return None

                            if resp.status_code == 503:
                                logger.warning(f"Google 503 for {url[:50]}... Attempt {i+1}/{attempts}")
                                redis.incrby("nexus:global_503_count", 1)
                                redis.expire("nexus:global_503_count", 60)
                                time.sleep(backoff)
                                backoff *= 2
                                continue

                            resp.raise_for_status()
                    except Exception as e:
                        if i == attempts - 1:
                            logger.error(f"Failed to fetch Google RSS after {attempts} attempts: {e}")
                        time.sleep(backoff)
                        backoff *= 2

                return None

            result = _try_fetch(client_args)

            # Proxy failed (407 quota exhausted / repeated errors) — retry direct.
            if result is None and proxy:
                logger.info(f"Proxy fetch failed for {url[:50]}. Retrying without proxy.")
                result = _try_fetch({"timeout": 30, "follow_redirects": True})

        return result
