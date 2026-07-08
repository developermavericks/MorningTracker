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
_GROQ_HAIKU_MODEL = os.getenv("GROQ_PRIMARY_MODEL") or "openai/gpt-oss-120b"  # Model used in Client Automation
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


def _call_llm(messages: List[dict], max_tokens: int = 150, temperature: float = 0.2, system_prompt: Optional[str] = None) -> Optional[str]:
    """
    Call LLM. Tries Claude first. If Claude fails or is not configured, falls back to Hugging Face.
    """
    # 1. Try Claude first
    if _ANTHROPIC_API_KEY:
        try:
            resp = _call_claude(messages, system_prompt=system_prompt, max_tokens=max_tokens, temperature=temperature)
            if resp:
                return resp
            logger.warning("[Heavy LLM] Claude call returned empty, trying Hugging Face fallback...")
        except Exception as e:
            logger.error(f"[Heavy LLM] Claude call failed: {e}. Trying Hugging Face fallback...")

    # 2. Try Hugging Face fallback
    if _HF_TOKEN:
        hf_messages = list(messages)
        if system_prompt:
            hf_messages.insert(0, {"role": "system", "content": system_prompt})
        return _call_hf(hf_messages, max_tokens, temperature)

    logger.warning("[Heavy LLM] Neither Claude nor Hugging Face is configured or succeeded.")
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

    resp = _call_hf(
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
    Generate a 30-40 words summary for an article using Groq (fallback to standard LLM).
    """
    prompt = f"""Summarize this news article in 30-40 words.

Title: {title}

Body:
{(body or "")[:2000]}

Respond with ONLY the summary, no quotes or markdown."""

    resp = _call_groq(
        [{"role": "user", "content": prompt}],
        max_tokens=800,
        temperature=0.3,
    )

    if not resp:
        logger.warning("[Heavy LLM] Groq summary failed or not configured, falling back to standard LLM.")
        resp = _call_llm(
            [{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.3,
        )

    return resp


_ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY") or ""
_ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8")
_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


def _call_claude(messages: List[dict], system_prompt: Optional[str] = None, max_tokens: int = 1000, temperature: float = 0.2) -> Optional[str]:
    """
    Make an Anthropic Messages API call. Returns the assistant's text response.
    """
    if not _ANTHROPIC_API_KEY:
        logger.warning("[Heavy LLM] No Anthropic API key configured. Falling back to other models.")
        return None

    try:
        headers = {
            "x-api-key": _ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": _ANTHROPIC_MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if "opus" not in _ANTHROPIC_MODEL.lower():
            payload["temperature"] = temperature
        if system_prompt:
            payload["system"] = system_prompt

        with httpx.Client(timeout=45) as client:
            resp = client.post(_ANTHROPIC_URL, headers=headers, json=payload)
            if resp.status_code == 200:
                return resp.json()["content"][0]["text"].strip()
            else:
                logger.error(f"[Heavy LLM] Anthropic API error {resp.status_code}: {resp.text[:500]}")
                return None
    except Exception as e:
        logger.error(f"[Heavy LLM] Anthropic call failed: {e}")
        return None


def generate_executive_summary(articles: List[dict], company_name: str = "Google") -> Optional[str]:
    """
    Generate a formatted executive summary using Claude, prioritizing priority media publications.
    """
    if not articles:
        return None

    # Sort articles: priority media first
    sorted_articles = sorted(articles, key=lambda x: 1 if x.get("_is_priority") else 0, reverse=True)

    article_text_list = []
    for idx, a in enumerate(sorted_articles, start=1):
        is_p = "[PRIORITY MEDIA]" if a.get("_is_priority") else "[NORMAL MEDIA]"
        pub = a.get("agency") or a.get("publication") or "Unknown Publication"
        title = a.get("title")
        summary = a.get("_summary", a.get("summary") or "")
        # Token optimization: truncate summary to max 400 characters to keep payload cost-effective
        if len(summary) > 400:
            summary = summary[:400].strip() + "..."

        article_text_list.append(
            f"Article #{idx} {is_p}\n"
            f"Publication: {pub}\n"
            f"Title: {title}\n"
            f"Summary: {summary}\n"
        )
    article_text = "\n".join(article_text_list)

    system_prompt = (
        "You are a premium news intelligence editor. Write a concise, client-presentable, executive briefing summary "
        f"for the daily {company_name} news tracker."
    )

    prompt = f"""Based on the following relevant news articles, generate exactly six headline developments.
Prefer articles from [PRIORITY MEDIA] sources whenever possible.

Articles list:
{article_text}

FORMAT REQUIREMENTS:
- Your response MUST start exactly with the line:
"Six headline developments shaping {company_name} India's strategic landscape today:"
- Followed by exactly six news cards.
- Each card MUST have a capitalized short label (e.g. "DATA CENTRE", "$40B DEAL", "MILITARY AI", "SEOUL CAMPUS", "AD SPEND", "CYBER ALERT") representing the topic.
- Followed by a concise 1-2 sentence description summarizing the core development and its relevance/implication.
- Separate cards by an empty line.

Example structure:
Six headline developments shaping {company_name} India's strategic landscape today:

DATA CENTRE
AP Pollution Control Board grants Consent to Establishment for 2 Google Data Centre sites in Vizag (Rambilli & Tarluvada). CM Naidu to lay foundation stone.

$40B DEAL
Google / Alphabet commits $10B immediately and up to $40B total in Anthropic at $350B valuation, deepening AI partnership.

Return ONLY the formatted text without any introductory conversational prefixes or markdown formatting."""

    return _call_llm(
        [{"role": "user", "content": prompt}],
        system_prompt=system_prompt,
        max_tokens=1000
    )


def generate_strategic_takeaways(articles: List[dict], company_name: str = "Google") -> Optional[str]:
    """
    Generate key takeaways using Claude, prioritizing priority media publications.
    """
    if not articles:
        return None

    # Sort articles: priority media first
    sorted_articles = sorted(articles, key=lambda x: 1 if x.get("_is_priority") else 0, reverse=True)

    article_text_list = []
    for idx, a in enumerate(sorted_articles, start=1):
        is_p = "[PRIORITY MEDIA]" if a.get("_is_priority") else "[NORMAL MEDIA]"
        pub = a.get("agency") or a.get("publication") or "Unknown Publication"
        title = a.get("title")
        summary = a.get("_summary", a.get("summary") or "")
        # Token optimization: truncate summary to max 400 characters to keep payload cost-effective
        if len(summary) > 400:
            summary = summary[:400].strip() + "..."

        article_text_list.append(
            f"Article #{idx} {is_p}\n"
            f"Publication: {pub}\n"
            f"Title: {title}\n"
            f"Summary: {summary}\n"
        )
    article_text = "\n".join(article_text_list)

    system_prompt = (
        "You are a premium strategic intelligence advisor. Extract key strategic takeaways "
        f"for {company_name} from the daily news coverage."
    )

    prompt = f"""Based on the following news articles, formulate exactly six key strategic takeaways/insights for {company_name}.
Prefer articles from [PRIORITY MEDIA] sources whenever possible.

Articles list:
{article_text}

FORMAT REQUIREMENTS:
- Your response MUST consist of exactly six bullet points/takeaways.
- Each takeaway must start with a bold key concept title, followed by a dash (—) or colon (:), and then a 1-2 sentence analytical insight explaining the strategic/regulatory/market implication for {company_name}.
- Do NOT include any intro or outro text, return ONLY the six takeaways.

Example format:
Vizag Data Centre Momentum — Regulatory & Political
With APPCB granting CTE orders for two of three sites, and CM Naidu personally committing to the foundation-laying on April 28, Google's 1-GW AI Data Centre Hub in Visakhapatnam is now firmly in execution phase.

The Anthropic Bet — $40B at $350B Valuation
Google's commitment of up to $40 billion in Anthropic (with $10B now in cash and $30B performance-linked) represents the largest single AI-infrastructure bet by a tech major in 2026.

Return ONLY the formatted takeaways."""

    return _call_llm(
        [{"role": "user", "content": prompt}],
        system_prompt=system_prompt,
        max_tokens=1000
    )


def verify_article_keyword_with_claude(title: str, matched_keyword: str) -> bool:
    """
    Asks Claude if the article title is truly relevant to the matched keyword.
    Returns True if relevant, False otherwise.
    """
    system_prompt = "You are a precise news filtering assistant. Decide if the news article title is genuinely relevant to the matched keyword."
    prompt = f"""Article Title: {title}
Matched Keyword: {matched_keyword}

Decide if this article is relevant. 

CRITICAL RULE: If the article title directly mentions the company "Google" or its core products/executives (such as Android, YouTube, Pixel, Gemini, Waymo, Sundar Pichai), it is ALWAYS relevant (answer "yes").

Otherwise, is it genuinely relevant to the matched keyword "{matched_keyword}"?

Answer "yes" if:
- It mentions Google, Android, YouTube, Pixel, Gemini, CCI cases involving Google, etc.
- It is a genuine match for the keyword.

Answer "no" ONLY if the match is a coincidental substring match, horoscope, or completely unrelated to Google (for example:
- "nothing to fear" matching "nothing ear"
- "opposition to" matching "oppo india"
- "open letter" matching "open ai"
- "Gemini horoscope/astrology"
- "skills" matching "skills india"
- "policy" matching "ai policy india" when it is about land-use).

Answer with ONLY "yes" or "no"."""

    resp = _call_claude([{"role": "user", "content": prompt}], system_prompt=system_prompt, max_tokens=10, temperature=0.1)
    if not resp:
        # If Claude fails, try Hugging Face fallback
        resp = _call_llm([{"role": "user", "content": prompt}], system_prompt=system_prompt, max_tokens=10, temperature=0.1)
        
    if resp:
        return "yes" in resp.lower()
    return True  # fallback to keeping the article if LLM call fails completely
