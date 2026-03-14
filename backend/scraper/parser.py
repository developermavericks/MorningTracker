"""
Single source of truth for all HTML parsing, extraction, and filtering.
Consolidates logic from engine.py and enrichment.py.
"""
import json
import re
import logging
from datetime import datetime
from typing import Optional, List, Dict
from bs4 import BeautifulSoup
import trafilatura

logger = logging.getLogger("PARSER")

JUNK_PATTERNS = [
    "google news", "continue reading in the app", "enable javascript", "consent.google",
    "please enable javascript", "subscribe to read", "you have reached your article limit",
    "this content is for subscribers", "access to this page has been denied", "403 forbidden",
    "404 not found", "page not found", "whatsapp\ntwitter\nfacebook\ne-mail",
    "one more step", "please complete the security check", "checking your browser",
    "ray id", "why do i have to complete a captcha", "hcaptcha", "recaptcha",
    "just a moment...", "attention required", "please verify you are a human",
    "unusual traffic from your computer network", "our systems have detected unusual traffic",
    "the block will expire shortly", "webcache.googleusercontent.com",
    "requests coming from your computer network", "archive.ph/newest", "error 429",
    "too many requests", "rate limit exceeded", "detected unusual traffic",
    "access denied", "robot check", "captcha", "security challenge",
    "javascript is disabled", "please turn on javascript",
    "cookies are disabled", "enable cookies to continue",
]

def clean_author_text(text: Optional[str]) -> Optional[str]:
    if not text: return None
    text = text.strip()
    if text.startswith('{') or text.startswith('[') or 'function(' in text or 'var ' in text: return None
    if len(text) > 120 or '\n' in text: return None
    if text.lower() in ["admin", "staff", "editor", "contributor", "corporate", "none", "null"]: return None
    return text

def is_junk_body(body: Optional[str], brand_keywords: List[str] = None) -> bool:
    if not body or len(body.strip()) < 100: return True
    
    body_lower = body.lower()
    # Brand Tracker Override: If the brand is mentioned, ignore noisy junk patterns
    if brand_keywords:
        if any(kw.lower() in body_lower for kw in brand_keywords):
            critical_blocks = ["404 not found", "403 forbidden", "access denied", "robot check"]
            if any(pb in body_lower for pb in critical_blocks): return True
            return False

    word_count = len(body.split())
    if word_count < 80: return True
    return any(pat in body_lower for pat in JUNK_PATTERNS)

def extract_author(html: str) -> Optional[str]:
    try:
        soup = BeautifulSoup(html, "lxml")
        # 1. JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") in ["Article", "NewsArticle", "BlogPosting", "WebPage"]:
                        auth_data = item.get("author")
                        if isinstance(auth_data, dict):
                            res = clean_author_text(auth_data.get("name"))
                            if res: return res
                        elif isinstance(auth_data, list) and auth_data:
                            for a in auth_data:
                                name = a.get("name") if isinstance(a, dict) else a
                                res = clean_author_text(name)
                                if res: return res
                        elif isinstance(auth_data, str):
                            res = clean_author_text(auth_data)
                            if res: return res
            except: continue
        
        # 2. Meta Tags
        for attr in ["name", "property"]:
            for val in ["author", "article:author", "og:article:author", "dc.creator", "sailthru.author"]:
                tag = soup.find("meta", {attr: val})
                if tag and tag.get("content"):
                    res = clean_author_text(tag["content"])
                    if res: return res

        # 3. CSS Selectors
        for sel in [".author", ".byline", ".entry-author", ".article-author", '[rel="author"]']:
            el = soup.select_one(sel)
            if el:
                res = clean_author_text(el.get_text(strip=True))
                if res: return res
    except: pass
    return None

def extract_date(html: str) -> Optional[datetime]:
    try:
        soup = BeautifulSoup(html, "lxml")
        # 1. JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") in ["Article", "NewsArticle", "BlogPosting", "WebPage"]:
                        for date_key in ["datePublished", "dateCreated", "pubDate"]:
                            if item.get(date_key):
                                return datetime.fromisoformat(item[date_key].replace('Z', '+00:00'))
            except: continue
            
        # 2. Meta Tags
        for attr in ["name", "property"]:
            for val in ["article:published_time", "pubdate", "publish-date", "og:article:published_time", "date"]:
                tag = soup.find("meta", {attr: val})
                if tag and tag.get("content"):
                    try:
                        return datetime.fromisoformat(tag["content"].replace('Z', '+00:00'))
                    except: pass
    except: pass
    return None

def extract_body(html: str) -> str:
    # 1. Trafilatura bare extraction
    try:
        res = trafilatura.bare_extraction(html)
        if res and res.get('text') and len(res.get('text')) > 400:
            return res.get('text')
    except: pass

    # 2. JSON-LD articleBody
    try:
        soup = BeautifulSoup(html, "lxml")
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") in ["Article", "NewsArticle", "BlogPosting"]:
                        body = item.get("articleBody")
                        if body and len(body) > 400: return body
            except: continue
    except: pass

    # 3. Trafilatura standard
    try:
        ext = trafilatura.extract(html, include_comments=False, no_fallback=False)
        if ext and len(ext) > 400: return ext
    except: pass

    return ""
