import httpx
import base64
import re
from typing import Optional

def decode_google_news_url(url: str) -> Optional[str]:
    """
    Decodes the base64 encoded part of a Google News redirect URL.
    This is much faster than using a browser.
    """
    try:
        if "/articles/" not in url:
            return None
        
        # Extract the base64 part
        encoded = url.split("/articles/")[1].split("?")[0]
        
        # Add padding if needed
        padded = encoded + "=="
        
        # Decode base64
        decoded = base64.urlsafe_b64decode(padded)
        
        # Google News encodes the URL in a binary format. 
        # We search for the first occurrence of 'http'
        match = re.search(rb"https?://[^\x00-\x1F\x7F]+", decoded)
        if match:
            return match.group(0).decode("utf-8", errors="ignore")
    except Exception:
        pass
    return None

async def resolve_google_news_url(url: str) -> str:
    """
    Tries to resolve the real URL behind a Google or Bing tracking link.
    First tries decoding (Google only), then a fast HTTP redirect resolution.
    """
    # 1. Try decoding (Instant, Google specific)
    if "news.google.com" in url:
        decoded = decode_google_news_url(url)
        if decoded:
            return decoded
    
    # 2. HTTP redirect resolution (Generic)
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        }
        async with httpx.AsyncClient(follow_redirects=True, timeout=8) as client:
            # HEAD is faster and often sufficient for resolving redirects
            try:
                resp = await client.head(url, headers=headers)
                if resp.status_code < 400:
                    return str(resp.url)
            except: pass
            
            # Fallback to GET if HEAD is blocked
            resp = await client.get(url, headers=headers)
            
            # Bot detection or Rate Limit check (Google/Bing specific signals)
            if resp.status_code == 503 or "google.com/images/errors/robot.png" in resp.text:
                return url
                
            return str(resp.url)
    except Exception:
        return url
