import httpx
import base64
import re
import random
import logging
from typing import Optional
from urllib.parse import urlparse

_logger = logging.getLogger("scraper.google_news")


def _is_google_domain(url: str) -> bool:
    """Returns True if the URL is still on a Google-owned domain."""
    try:
        host = urlparse(url).netloc.lower()
        return "google.com" in host or "googleapis.com" in host
    except Exception:
        return False


def _extract_url_from_google_page(html: str) -> Optional[str]:
    """
    Try to extract the actual article URL from a Google News redirect page.
    Handles 'Redirect notice' pages and JS-redirect article pages.
    """
    try:
        # Pattern 1: "Redirect notice" page — "trying to send you to <a href='URL'>"
        m = re.search(
            r'trying to send you to[^<]*<[^>]*href=["\']?(https?://[^"\'>\s]+)',
            html, re.IGNORECASE
        )
        if m:
            candidate = m.group(1)
            if not _is_google_domain(candidate):
                return candidate

        # Pattern 2: JavaScript window.location redirect
        m = re.search(
            r'window\.location(?:\.href)?\s*=\s*["\']?(https?://[^"\';\s]+)',
            html
        )
        if m:
            candidate = m.group(1)
            if not _is_google_domain(candidate):
                return candidate

        # Pattern 3: meta refresh redirect
        m = re.search(
            r'<meta[^>]+http-equiv=["\']?refresh["\']?[^>]+url=(https?://[^"\';\s>]+)',
            html, re.IGNORECASE
        )
        if m:
            candidate = m.group(1)
            if not _is_google_domain(candidate):
                return candidate

    except Exception:
        pass
    return None


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
        match = re.search(rb"https?://[^\x00-\x1F\x7F\x80-\xFF]{10,}", decoded)
        if match:
            candidate = match.group(0).decode("utf-8", errors="ignore").rstrip(".,;)")
            if not _is_google_domain(candidate):
                return candidate
    except Exception:
        pass
    return None


def resolve_google_news_url_sync(url: str) -> str:
    """
    Resolves a Google News RSS redirect URL to the actual article URL.
    Returns the resolved URL, or "" if the URL cannot be resolved beyond Google's domain
    (caller should skip the article rather than scraping a redirect page).
    Returns the original URL unchanged for non-Google URLs.
    """
    if not url:
        return ""

    is_google_news = "news.google.com" in url

    # 1. Try googlenewsdecoder library
    if is_google_news:
        try:
            from scraper.engine import load_proxies
            import googlenewsdecoder
            proxies = load_proxies()
            proxy_url = proxies[0] if proxies else None
            res = googlenewsdecoder.gnewsdecoder(url, proxy=proxy_url)
            if res.get("status") and res.get("decoded_url"):
                resolved = res["decoded_url"]
                if not _is_google_domain(resolved):
                    return resolved
            else:
                _logger.warning(f"googlenewsdecoder failed: {res.get('message') or res}")
        except Exception as e:
            _logger.error(f"googlenewsdecoder error: {e}", exc_info=True)

    # 2. Base64 decoder fallback (offline, no network)
    if is_google_news:
        decoded = decode_google_news_url(url)
        if decoded:
            _logger.info(f"Base64 decoded Google News URL: {decoded}")
            return decoded

    # 3. HTTP redirect resolution
    try:
        from scraper.engine import load_proxies
        proxies = load_proxies()
        proxy_url = proxies[0] if proxies else None

        headers = {
            "User-Agent": random.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.6533.120 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.6533.120 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.6478.229 Safari/537.36",
            ]),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        client_kwargs = {"follow_redirects": True, "timeout": httpx.Timeout(12.0, connect=8.0)}
        if proxy_url:
            client_kwargs["proxy"] = proxy_url

        with httpx.Client(**client_kwargs) as client:
            # HEAD first — only trust result if it resolved AWAY from Google domains.
            # Google often returns 200 on the intermediate /articles/ page (JS redirect),
            # which would still be a google.com URL — we must not use that as the final URL.
            try:
                resp = client.head(url, headers=headers)
                final_url = str(resp.url)
                if resp.status_code < 400 and not _is_google_domain(final_url):
                    return final_url
            except Exception:
                pass

            # GET with redirect following
            resp = client.get(url, headers=headers)

            # Rate-limited or bot-detected by Google
            if resp.status_code == 503 or "google.com/images/errors/robot.png" in resp.text:
                _logger.warning(f"Google rate-limited/bot-detected for URL: {url}")
                # For non-Google URLs, return as-is; for Google URLs, signal failure
                return "" if is_google_news else url

            final_url = str(resp.url)

            # If still on Google domain, try to extract the actual URL from page content.
            # This handles both JS-redirect article pages and "Redirect notice" pages.
            if _is_google_domain(final_url):
                extracted = _extract_url_from_google_page(resp.text)
                if extracted:
                    _logger.info(f"Extracted URL from Google page content: {extracted}")
                    return extracted
                # Could not resolve beyond Google — signal failure so caller skips the article
                _logger.warning(f"Could not resolve Google News URL beyond Google domain: {url}")
                return ""

            return final_url

    except Exception as ex:
        _logger.error(f"URL resolution exception for {url}: {ex}")
        # For non-Google URLs, return as-is; for Google URLs that failed, signal failure
        return "" if is_google_news else url
