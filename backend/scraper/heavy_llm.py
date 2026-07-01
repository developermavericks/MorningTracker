"""
Heavy Automation LLM integration for Phase 4.

Uses Groq Haiku (cheap, fast) for:
  - Ambiguous-middle article judgment
  - Per-article summaries
  - Executive Summary generation
  - Strategic Takeaways
"""

import json
import logging
import httpx
import random
import os
import time
from typing import Optional, Dict, List, Tuple
from dotenv import load_dotenv

env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(env_path)

logger = logging.getLogger(__name__)

# Groq API setup (reuse from scraper/llm.py patterns)
_GROQ_API_KEYS = [k.strip() for k in (os.getenv("GROQ_API_KEY") or "").split(",") if k.strip()]
_GROQ_HAIKU_MODEL = "openai/gpt-oss-20b"  # Cheap, fast model (Groq compatible)
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Hugging Face Setup
_HF_TOKEN = os.getenv("HF_TOKEN")
_HF_MODEL = os.getenv("HF_MODEL_ID", "meta-llama/Llama-3.1-8B-Instruct")
_HF_URL = "https://router.huggingface.co/v1/chat/completions"


def _call_groq(messages: List[dict], max_tokens: int = 150, temperature: float = 0.2) -> Optional[str]:
    """
    Make a single Groq API call. Returns text response or None on failure.
    """
    if not _GROQ_API_KEYS:
        logger.warning("[Heavy LLM] No Groq API keys configured")
        return None

    try:
        api_key = random.choice(_GROQ_API_KEYS)
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": _GROQ_HAIKU_MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        with httpx.Client(timeout=20) as client:
            resp = client.post(_GROQ_URL, headers=headers, json=payload)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
            elif resp.status_code == 429:
                time.sleep(2)
                return None
            else:
                logger.warning(f"[Heavy LLM] Groq error {resp.status_code}: {resp.text[:200]}")
                return None
    except Exception as e:
        logger.error(f"[Heavy LLM] Groq call failed: {e}")
        return None


def _call_hf(messages: List[dict], max_tokens: int = 150, temperature: float = 0.2) -> Optional[str]:
    """
    Make a Hugging Face Serverless Inference API call.
    """
    if not _HF_TOKEN:
        logger.warning("[Heavy LLM] No Hugging Face token configured")
        return None

    try:
        headers = {
            "Authorization": f"Bearer {_HF_TOKEN}",
            "Content-Type": "application/json",
            "x-wait-for-model": "true"
        }
        payload = {
            "model": _HF_MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        with httpx.Client(timeout=30, verify=False, follow_redirects=True) as client:
            resp = client.post(_HF_URL, headers=headers, json=payload)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
            else:
                logger.warning(f"[Heavy LLM] Hugging Face error {resp.status_code}: {resp.text[:200]}")
                return None
    except Exception as e:
        logger.error(f"[Heavy LLM] Hugging Face call failed: {e}")
        return None


def _call_llm(messages: List[dict], max_tokens: int = 150, temperature: float = 0.2) -> Optional[str]:
    """
    Call LLM. Uses Hugging Face. Groq fallback is disabled per user request.
    """
    if _HF_TOKEN:
        return _call_hf(messages, max_tokens, temperature)
    logger.warning("[Heavy LLM] Groq API fallback is disabled in heavy automation.")
    return None


def judge_ambiguous_article(title: str, body: str, context: str = "") -> Tuple[bool, Optional[str]]:
    """
    For ambiguous_middle articles: decide keep/discard and return pillar assignment.
    Returns (keep: bool, pillar: str or None).
    """
    prompt = f"""You are a news relevance analyst. Given an article, decide if it's actually about Google/competitors or just mentions them in passing.

Article Title: {title}

Article Body (first 1000 chars):
{(body or "")[:1000]}

Context: {context or "Generic technology company"}

Respond ONLY with JSON, no markdown:
{{"keep": true/false, "pillar": "pillar_name_or_null"}}

If keep=true, suggest which pillar (e.g., "Policy / Regulation / Legal", "Google News Initiatives", "Online Safety Initiatives", "Digital / Skilling", "Startup Ecosystem", "Developer Platforms & Products", "Foundational Models & AI Research", "Education Platforms & Products", "Google Products (Misc)", "Corporate Comms", "Product & Consumer - YouTube", "Product & Consumer - Devices & Hardware", "Product & Consumer - Consumer Products", "Competitor Category").

If keep=false, pillar should be null."""

    resp = _call_llm(
        [{"role": "user", "content": prompt}],
        max_tokens=100,
        temperature=0.1,
    )

    if not resp:
        # Conservative fallback: keep and assume best guess
        return True, "Other"

    try:
        data = json.loads(resp)
        return data.get("keep", True), data.get("pillar")
    except json.JSONDecodeError:
        logger.warning(f"[Heavy LLM] Failed to parse ambiguous judgment response: {resp}")
        return True, "Other"


def summarize_article(title: str, body: str) -> Optional[str]:
    """
    Generate a 1-2 sentence summary + "so what" for an article.
    """
    prompt = f"""Summarize this news article in 1-2 sentences. Include "so what" insight at the end.

Title: {title}

Body:
{(body or "")[:2000]}

Respond with ONLY the summary, no quotes or markdown."""

    return _call_llm(
        [{"role": "user", "content": prompt}],
        max_tokens=100,
        temperature=0.3,
    )


def generate_executive_summary(articles: List[dict], company_name: str = "Google") -> Optional[str]:
    """
    Generate a 3-4 sentence executive summary from top 5 articles.
    """
    if not articles:
        return None

    top_articles = articles[:5]
    article_text = "\n\n".join([
        f"Title: {a.get('title')}\nSummary: {a.get('_summary', a.get('summary'))}"
        for a in top_articles
    ])

    prompt = f"""You are a news intelligence analyst. Write a 3-4 sentence executive summary for a daily {company_name} India briefing based on these top articles:

{article_text}

Focus on: major news, implications, strategic importance. Respond with ONLY the summary, no quotes or markdown."""

    return _call_llm(
        [{"role": "user", "content": prompt}],
        max_tokens=150,
        temperature=0.3,
    )


def generate_strategic_takeaways(articles: List[dict], company_name: str = "Google") -> Optional[str]:
    """
    Generate 3-4 bullet points of strategic/regulatory takeaways from policy articles.
    """
    policy_articles = [a for a in articles if a.get("_pillar") == "Policy / Regulation / Legal"]
    if not policy_articles:
        return None

    article_text = "\n".join([
        f"- {a.get('title')}: {a.get('_summary', a.get('summary'))}"
        for a in policy_articles[:5]
    ])

    prompt = f"""Extract 3-4 key strategic/regulatory takeaways for {company_name} from these policy-related articles:

{article_text}

Format as bullet points. Respond with ONLY the bullets, no quotes or markdown."""

    return _call_llm(
        [{"role": "user", "content": prompt}],
        max_tokens=200,
        temperature=0.2,
    )
