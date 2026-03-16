import os
import random
import asyncio
import httpx
import json
import time
from typing import Optional, List, Dict, Any
import ollama

# --- Configuration ---
GROQ_API_KEYS = [k.strip() for k in os.getenv("GROQ_API_KEY", "").split(",") if k.strip()]
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "minimax-m2:cloud")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# --- Redis for Global Throttling (C-7) ---
import redis.asyncio as redis
_redis_client = None

async def get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
    return _redis_client

# Synchronous Redis for gevent workers
import redis as redis_sync
_redis_sync_client = None

def get_redis_sync():
    global _redis_sync_client
    if _redis_sync_client is None:
        _redis_sync_client = redis_sync.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
    return _redis_sync_client

_ollama_semaphore = None
def get_ollama_semaphore():
    global _ollama_semaphore
    if _ollama_semaphore is None:
        _ollama_semaphore = asyncio.Semaphore(2) # Throttles to max 2 concurrent LLM requests to prevent connection closure on mid-range hardware
    return _ollama_semaphore

def log(msg: str):
    from scraper.engine import logger
    logger.info(msg)

# --- Groq Client ---
def summarize_with_groq_sync(text: str) -> Optional[str]:
    is_placeholder = any("your_groq_api_key" in k.lower() for k in GROQ_API_KEYS)
    if not GROQ_API_KEYS or is_placeholder or not text or len(text) < 400: return None
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "You are a news analyst. Summarize this article into EXACTLY 3 bullet points. Output only the bullet points."},
            {"role": "user", "content": text[:4000]},
        ],
        "max_tokens": 150,
    }

    with httpx.Client(timeout=30) as client:
        for attempt in range(3):
            r = get_redis_sync()
            GROQ_LIMIT_KEY = "nexus:groq_global_throttle"
            req_count = r.incr(GROQ_LIMIT_KEY)
            if req_count == 1: r.expire(GROQ_LIMIT_KEY, 60)
            
            if req_count > 30:
                time.sleep(1)
                continue

            api_key = random.choice(GROQ_API_KEYS)
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            try:
                resp = client.post(url, headers=headers, json=payload, timeout=15)
                if resp.status_code == 200: return resp.json()["choices"][0]["message"]["content"]
                elif resp.status_code == 429: time.sleep(2 ** attempt)
                else: break
            except: time.sleep(1)
    return None

# --- Ollama Client ---
from urllib.parse import urlparse

def get_domain_name(url: str) -> str:
    """Extract a clean domain name from a URL."""
    try:
        domain = urlparse(url).netloc
        if domain.startswith("www."):
            domain = domain[4:]
        # Remove TLD for a cleaner 'Agency' name if needed, or keep it.
        # Let's keep it but capitalized for common ones.
        parts = domain.split('.')
        if len(parts) > 1:
            return parts[-2].capitalize()
        return domain.capitalize()
    except:
        return ""

def extract_metadata_with_ollama_sync(body: str, url: str = "", context_agency: str = "") -> Dict[str, Any]:
    if not body or len(body) < 100: return {"author": None, "agency": None, "body": body}
    domain = get_domain_name(url) if url else ""
    prompt = f"Analyze article and extract JSON: author, agency, is_junk, cleaned_body. Source Info: URL={url}, Domain={domain}. Text: {body[:6000]}"
    try:
        client = ollama.Client(host=OLLAMA_BASE_URL)
        response = client.chat(model=OLLAMA_MODEL, messages=[{'role': 'user', 'content': prompt}], format='json')
        content = response['message']['content']
        data = json.loads(content)
        res_agency = data.get("agency") or domain
        return {"author": data.get("author"), "agency": res_agency, "is_junk": data.get("is_junk", False), "cleaned_body": data.get("cleaned_body", body)}
    except Exception as e:
        log(f"Ollama Extraction error: {e}")
        return {"author": None, "agency": domain, "body": body}

def perform_full_enrichment_sync(body: str, title: str, url: str, sector: str) -> Dict[str, Any]:
    results = {"summary": None, "author": None, "agency": None, "tags": None, "sentiment": "neutral"}
    if not body or len(body) < 100: return results
    meta = extract_metadata_with_ollama_sync(body, url=url)
    results["author"] = meta.get("author")
    results["agency"] = meta.get("agency")
    results["summary"] = summarize_with_groq_sync(body)
    if "positive" in body.lower()[:500]: results["sentiment"] = "positive"
    if "warning" in body.lower()[:500]: results["sentiment"] = "negative"
    return results
