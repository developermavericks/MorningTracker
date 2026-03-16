import logging
import sys
import json
import subprocess
import os

logger = logging.getLogger(__name__)

def scrape_url(url: str, timeout: int = 45000) -> str | None:
    """
    Runs Playwright in a completely isolated OS process via subprocess.
    This guarantees zero event loop collisions with Gevent/Celery.
    """
    script_path = os.path.join(os.path.dirname(__file__), "playwright_worker.py")
    
    logger.info(f"Subprocess scraper: Navigating to {url}")
    try:
        proc = subprocess.run(
            [sys.executable, script_path, url, str(timeout)],
            capture_output=True,
            text=True,
            timeout=(timeout / 1000) + 15
        )
        
        if proc.returncode != 0 and not proc.stdout.strip():
            logger.error(f"Scraper process failed for {url}: {proc.stderr}")
            return None
            
        out = proc.stdout.strip()
        if not out:
            logger.error(f"Scraper process returned empty output for {url}")
            return None
            
        try:
            # Output might have trailing newlines or other prints, safely take the last valid JSON line
            lines = [line for line in out.splitlines() if line.strip()]
            data = json.loads(lines[-1])
            if data.get("error"):
                logger.error(f"Scraper error for {url}: {data['error']}")
                return None
            return data.get("content")
        except json.JSONDecodeError:
            logger.error(f"Scraper process returned invalid JSON for {url}: {out}\nStderr: {proc.stderr}")
            return None
            
    except subprocess.TimeoutExpired:
        logger.error(f"Scraper process timed out for {url}")
        return None
    except Exception as e:
        logger.error(f"Scraper OS error for {url}: {str(e)}")
        return None
