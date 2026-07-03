import os
import random
import asyncio
import httpx
import json
import time
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

# Initialize environment variables
load_dotenv()

# --- Configuration ---
# Support GROQ_API_KEY or XAI_API_KEY (legacy name) for Groq credentials
_groq_raw = os.getenv("GROQ_API_KEY") or os.getenv("XAI_API_KEY") or ""
GROQ_API_KEYS = [k.strip() for k in _groq_raw.split(",") if k.strip()]

GROQ_PRIMARY_MODEL = os.getenv("GROQ_PRIMARY_MODEL") or "openai/gpt-oss-120b"
GROQ_SECONDARY_MODEL = os.getenv("GROQ_SECONDARY_MODEL") or "openai/gpt-oss-120b"
# Faster model used exclusively for Stage-1 relevance classification.
# openai/gpt-oss-20b: 1000 T/sec, 2× faster and half the cost of 120B — ideal for binary classification.
# Stage-2 escalation uses GROQ_SECONDARY_MODEL (120B) for uncertain borderline cases.
# Override via GROQ_RELEVANCE_MODEL env var if needed.
GROQ_RELEVANCE_MODEL = os.getenv("GROQ_RELEVANCE_MODEL") or "openai/gpt-oss-20b"

# --- Redis for Global Throttling (C-7) ---
import redis.asyncio as redis
_redis_client = None

class DummyRedis:
    def __init__(self):
        self._data = {}
    async def get(self, key): return self._data.get(key)
    async def set(self, key, val, *args, **kwargs): self._data[key] = val; return True
    async def ping(self): return True
    async def sismember(self, name, val): return False
    async def sadd(self, name, *values): return 0
    # Fallback support
    def __getattr__(self, name):
        def _mock(*args, **kwargs):
            return None
        return _mock

class DummyRedisSync:
    def __init__(self):
        self._data = {}
    def get(self, key): return self._data.get(key)
    def set(self, key, val, *args, **kwargs): self._data[key] = val; return True
    def ping(self): return True
    def sismember(self, name, val): return False
    def sadd(self, name, *values): return 0
    # Fallback support
    def __getattr__(self, name):
        def _mock(*args, **kwargs):
            return None
        return _mock

async def get_redis():
    global _redis_client
    if _redis_client is None:
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        if not url or "localhost" in url or "127.0.0.1" in url:
            try:
                client = redis.from_url(url or "redis://localhost:6379/0", decode_responses=True)
                await asyncio.wait_for(client.ping(), timeout=2.0)
                _redis_client = client
            except Exception:
                print("Celery/LLM: Redis offline. Initializing Mock Async Redis.")
                _redis_client = DummyRedis()
        else:
            _redis_client = redis.from_url(url, decode_responses=True)
    return _redis_client

# Synchronous Redis for gevent workers
import redis as redis_sync
_redis_sync_client = None

def get_redis_sync():
    global _redis_sync_client
    if _redis_sync_client is None:
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        if not url or "localhost" in url or "127.0.0.1" in url:
            try:
                client = redis_sync.from_url(url or "redis://localhost:6379/0", decode_responses=True)
                client.ping()
                _redis_sync_client = client
            except Exception:
                print("Celery/LLM: Redis offline. Initializing Mock Sync Redis.")
                _redis_sync_client = DummyRedisSync()
        else:
            _redis_sync_client = redis_sync.from_url(url, decode_responses=True)
    return _redis_sync_client



def log(msg: str):
    from scraper.engine import logger
    logger.info(msg)



def clean_conversational_prefix(text: str) -> str:
    if not text:
        return ""
    import re
    # Strip common patterns like "Here is a summary of the article:", "Here is a summary:", "Summary:", etc.
    patterns = [
        r"^here\s+is\s+a\s+summary\s+of\s+the\s+article:?\s*",
        r"^here\s+is\s+a\s+summary:?\s*",
        r"^here\s+is\s+the\s+summary:?\s*",
        r"^summary:?\s*",
        r"^this\s+article:?\s*",
        r"^the\s+article\s+summarizes\s+that:?\s*",
        r"^the\s+article\s+reports\s+that:?\s*",
        r"^based\s+on\s+the\s+article,?\s*"
    ]
    cleaned = text.strip()
    for pattern in patterns:
        cleaned = re.compile(pattern, re.IGNORECASE).sub("", cleaned).strip()
    return cleaned

# Compatibility wrapper for existing callers
def validate_summary(summary: str, title: str, summary_length: int = 35) -> bool:
    if not summary:
        return False
    words = summary.strip().split()
    min_limit = max(10, summary_length - 15)
    max_limit = summary_length + 15
    if not (min_limit <= len(words) <= max_limit):
        return False
    clean_summary = summary.lower().strip().replace(".", "").replace(",", "").strip()
    clean_title = title.lower().strip().replace(".", "").replace(",", "").strip()
    if clean_summary == clean_title:
        return False
    if len(clean_summary) < len(clean_title) + 10 and clean_title in clean_summary:
        return False
    return True

def _call_groq_summary_api(text: str, is_strict: bool = False, summary_length: int = 35) -> Optional[str]:
    is_placeholder = any("your_groq_api_key" in k.lower() for k in GROQ_API_KEYS)
    if not GROQ_API_KEYS or is_placeholder:
        return None
        
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    min_words = max(5, summary_length - 5)
    max_words = summary_length
    system_content = (
        "You are a news analyst. Summarize this article. RULES: You MUST output strictly a single paragraph. "
        f"You MUST NOT use bullet points, lists, or line breaks. The summary MUST be between {min_words} to {max_words} words in length."
    )
    if is_strict:
        system_content += " IMPORTANT: Do NOT copy the article title. Write a fresh, independent summary."
        
    max_tokens = max(150, summary_length * 2)
    payload = {
        "model": GROQ_PRIMARY_MODEL,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": text[:4000]},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.1
    }

    with httpx.Client(timeout=30) as client:
        for attempt in range(2):
            api_key = random.choice(GROQ_API_KEYS)
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            try:
                resp = client.post(url, headers=headers, json=payload, timeout=15)
                if resp.status_code == 200:
                    summary = resp.json()["choices"][0]["message"]["content"].strip()
                    summary = summary.replace("\n", " ").replace("- ", "").replace("* ", "")
                    summary = clean_conversational_prefix(summary)
                    return summary
                elif resp.status_code == 429:
                    time.sleep(1)
                else:
                    break
            except:
                pass
    return None

def _call_groq_summary_120b(text: str, summary_length: int = 35) -> Optional[str]:
    is_placeholder = any("your_groq_api_key" in k.lower() for k in GROQ_API_KEYS)
    if not GROQ_API_KEYS or is_placeholder:
        return None
        
    url = "https://api.groq.com/openai/v1/chat/completions"
    min_words = max(5, summary_length - 5)
    max_words = summary_length
    max_tokens = max(150, summary_length * 2)
    payload = {
        "model": GROQ_SECONDARY_MODEL,
        "messages": [
            {
                "role": "system", 
                "content": f"You are a news analyst. Summarize this article. RULES: You MUST output strictly a single paragraph. The summary MUST be between {min_words} to {max_words} words in length."
            },
            {"role": "user", "content": text[:4000]},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.1
    }

    with httpx.Client(timeout=30) as client:
        for attempt in range(2):
            api_key = random.choice(GROQ_API_KEYS)
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            try:
                resp = client.post(url, headers=headers, json=payload, timeout=15)
                if resp.status_code == 200:
                    summary = resp.json()["choices"][0]["message"]["content"].strip()
                    summary = summary.replace("\n", " ").replace("- ", "").replace("* ", "")
                    summary = clean_conversational_prefix(summary)
                    return summary
                elif resp.status_code == 429:
                    time.sleep(1)
                else:
                    break
            except:
                pass
    return None

# Compatibility wrapper for existing callers
def summarize_with_groq_sync(text: str, title: str = "", summary_length: int = 35) -> Optional[str]:
    # 1. Try Groq (llama-3.3-70b-versatile)
    summary1 = _call_groq_summary_api(text, is_strict=False, summary_length=summary_length)
    if validate_summary(summary1, title, summary_length):
        return summary1

    # 2. Retry with stricter prompt
    log("Cheap model summary validation failed. Retrying with strict prompt...")
    summary2 = _call_groq_summary_api(text, is_strict=True, summary_length=summary_length)
    if validate_summary(summary2, title, summary_length):
        return summary2

    # 3. Fallback to 120B model block on Groq (using llama-3.3-70b-versatile)
    log("Falling back to secondary summary check...")
    summary3 = _call_groq_summary_120b(text, summary_length=summary_length)
    if validate_summary(summary3, title, summary_length):
        return summary3

    # If any summary was successfully generated by the API, return it even if it didn't pass strict validation.
    # A slightly off summary is much better than text truncation with ellipses.
    for candidate in [summary3, summary2, summary1]:
        if candidate:
            candidate_cleaned = candidate.replace("\n", " ").replace("- ", "").replace("* ", "").strip()
            # Remove trailing ellipses from model output if present
            if candidate_cleaned.endswith("..."):
                candidate_cleaned = candidate_cleaned[:-3].strip()
            # Ensure it ends with a period
            if candidate_cleaned and not candidate_cleaned.endswith("."):
                candidate_cleaned += "."
            return candidate_cleaned

    # Absolute fallback: construct a clean sentence-based summary matching summary_length
    sentences = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
    cleaned_fallback = []
    word_count = 0
    for s in sentences:
        s_words = s.split()
        if word_count + len(s_words) <= summary_length:
            cleaned_fallback.append(s)
            word_count += len(s_words)
        else:
            needed = summary_length - word_count
            if needed > 5:
                cleaned_fallback.append(" ".join(s_words[:needed]))
            break
            
    fallback_text = ". ".join(cleaned_fallback).strip()
    if not fallback_text:
        fallback_text = " ".join(text.split()[:summary_length])
    if not fallback_text.endswith("."):
        fallback_text += "."
    return fallback_text

def safe_json_parse(text: str) -> dict:
    import re
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)

def check_relevance_with_groq_oss(title: str, body: str, keywords: List[str], client_name: str, client_context: Optional[str] = None, use_120b: bool = False) -> tuple[str, str, float]:
    """
    Evaluates if the article is relevant using Groq SDK.
    Returns: (verdict, reason, score)
    """
    api_key = os.getenv("GROQ_RELEVANCE_API_KEY")
    is_placeholder = not api_key or "ReplaceMe" in api_key or "your_groq" in api_key.lower()
    if is_placeholder:
        api_key = GROQ_API_KEYS[0] if GROQ_API_KEYS else None
        is_placeholder = not api_key
        
    if is_placeholder or not body or not api_key:
        raise ValueError("No valid Groq API Key available for relevance check")
        
    context_str = ""
    if client_context:
        context_str = f"CLIENT CONTEXT & GUIDELINES:\n{client_context}\n\n"
    elif client_name.lower() == "scapia":
        context_str = (
            "CLIENT CONTEXT (About Scapia):\n"
            "Scapia is an Indian travel fintech company that offers a co-branded travel credit card designed for the modern Indian traveller. "
            "Scapia operates at the intersection of travel and rewards-led payments. The news surfaced must be useful for every team at Scapia, "
            "including cards and payments, hotels and stays, OTA, travel, and the PR/comms team. The tracker tracks and summarizes news under "
            "three daily sections:\n\n"
            "1. FinTech:\n"
            "   - Cover the payments, cards, and rewards ecosystem.\n"
            "   - Include important statements/regulations from RBI or regulatory bodies.\n"
            "   - Include launches of new cards, card products, and banks launching new offerings or partnerships.\n"
            "   - Include broader trends and conversations in the Indian fintech/payments industry.\n"
            "2. Travel:\n"
            "   - Cover the larger travel sector and industry evolution.\n"
            "   - Include emerging travel trends, new travel products, competitor moves/announcements, and notable travel campaigns.\n"
            "   - Include other signals showing how the travel sector is shaping up (e.g. footfalls, seasonal destination demand shifts).\n"
            "3. New Routes:\n"
            "   - Cover travel-related infrastructure and connectivity updates.\n"
            "   - Include new flight, train, or bus routes launched.\n"
            "   - Include new hotel partnerships and expansions, new property launches, and new airport openings.\n\n"
            "RELEVANCE RULES & EXCLUSIONS:\n"
            "- Allow general sector updates (fintech, cards, travel, and route launches) even if they do not directly mention Scapia.\n"
            "- Exclude stock market routine trading reports (except major IPOs).\n"
            "- Exclude routine internal operational updates (like airline fuel costs or routine HR appointments unless widely significant).\n"
            "- Exclude visa rejections/routine updates and medical/wellness exhibitions.\n"
            "- Exclude publications like Nomad Lawyer.\n\n"
        )
        
    # Stage-2 escalation uses the heavy model; Stage-1 uses the faster relevance model.
    model_name = GROQ_SECONDARY_MODEL if use_120b else GROQ_RELEVANCE_MODEL
    
    prompt = (
        f"You are an editor filtering news for the client '{client_name}'.\n\n"
        f"{context_str}"
        f"Target Keywords/Topics: {', '.join(keywords)}\n\n"
        f"Article Title: {title}\n"
        f"Article Content: {body[:5000]}\n\n"
        f"Determine if this article is relevant to '{client_name}' based on the context, guidelines, and target keywords.\n"
        f"RELEVANCE RULES:\n"
        f"1. Return 'relevant' ONLY if the article is clearly on-topic for the client's described sections and would be genuinely useful to the client's teams.\n"
        f"2. Return 'not_relevant' if the article is off-topic, only tangentially related, or not actionable/useful for the client.\n"
        f"3. Return 'uncertain' ONLY for genuinely borderline cases — not as a default for weak or indirect matches.\n\n"
        f"You MUST output strictly in JSON format. Do not write any explanations outside the JSON structure. Response format:\n"
        f'{{"verdict": "relevant" | "not_relevant" | "uncertain", "reason": "concise explanation", "score": float between 0.0 and 1.0}}'
    )

    from groq import Groq
    client = Groq(api_key=api_key)
    completion = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": "You are a strict JSON classifier. You must return a raw JSON object and absolutely nothing else. Do not wrap the JSON in markdown code blocks (such as ```json ... ```), do not write any introductory or concluding text, and do not explain your choice. Output valid JSON matching the schema."
            },
            {"role": "user", "content": prompt}
        ],
        temperature=0.0,
        max_completion_tokens=400,
        response_format={"type": "json_object"},
        top_p=1.0,
        stop=None
    )
    ans = completion.choices[0].message.content.strip()
    try:
        data = safe_json_parse(ans)
        verdict = str(data.get("verdict", "uncertain")).lower().strip()
        reason = str(data.get("reason", "No reason provided"))
        score = float(data.get("score", 0.5))
        return verdict, reason, score
    except Exception as e:
        log(f"Relevance JSON parse error: {e}. Raw: {ans}")
        ans_upper = ans.upper()
        if "NOT_RELEVANT" in ans_upper:
            return "not_relevant", "Regex match not_relevant", 0.1
        elif "RELEVANT" in ans_upper:
            return "relevant", "Regex match relevant", 0.9
        return "uncertain", "Fallback JSON parse failure", 0.5

def check_relevance_with_groq_fallback_http(title: str, body: str, keywords: List[str], client_name: str, client_context: Optional[str] = None, use_120b: bool = False) -> tuple[str, str, float]:
    """
    Evaluates relevance via direct HTTP call.
    Returns: (verdict, reason, score)
    """
    is_placeholder = any("your_groq_api_key" in k.lower() for k in GROQ_API_KEYS)
    if not GROQ_API_KEYS or is_placeholder or not body:
        return "uncertain", "Missing API key or empty body", 0.5
        
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    context_str = ""
    if client_context:
        context_str = f"CLIENT CONTEXT & GUIDELINES:\n{client_context}\n\n"
    elif client_name.lower() == "scapia":
        context_str = (
            "CLIENT CONTEXT (About Scapia):\n"
            "Scapia is an Indian travel fintech company that offers a co-branded travel credit card designed for the modern Indian traveller. "
            "Scapia operates at the intersection of travel and rewards-led payments. The news surfaced must be useful for every team at Scapia, "
            "including cards and payments, hotels and stays, OTA, travel, and the PR/comms team. The tracker tracks and summarizes news under "
            "three daily sections:\n\n"
            "1. FinTech:\n"
            "   - Cover the payments, cards, and rewards ecosystem.\n"
            "   - Include important statements/regulations from RBI or regulatory bodies.\n"
            "   - Include launches of new cards, card products, and banks launching new offerings or partnerships.\n"
            "   - Include broader trends and conversations in the Indian fintech/payments industry.\n"
            "2. Travel:\n"
            "   - Cover the larger travel sector and industry evolution.\n"
            "   - Include emerging travel trends, new travel products, competitor moves/announcements, and notable travel campaigns.\n"
            "   - Include other signals showing how the travel sector is shaping up (e.g. footfalls, seasonal destination demand shifts).\n"
            "3. New Routes:\n"
            "   - Cover travel-related infrastructure and connectivity updates.\n"
            "   - Include new flight, train, or bus routes launched.\n"
            "   - Include new hotel partnerships and expansions, new property launches, and new airport openings.\n\n"
            "RELEVANCE RULES & EXCLUSIONS:\n"
            "- Allow general sector updates (fintech, cards, travel, and route launches) even if they do not directly mention Scapia.\n"
            "- Exclude stock market routine trading reports (except major IPOs).\n"
            "- Exclude routine internal operational updates (like airline fuel costs or routine HR appointments unless widely significant).\n"
            "- Exclude visa rejections/routine updates and medical/wellness exhibitions.\n"
            "- Exclude publications like Nomad Lawyer.\n\n"
        )
        
    # Stage-2 escalation uses the heavy model; Stage-1 uses the faster relevance model.
    model_name = GROQ_SECONDARY_MODEL if use_120b else GROQ_RELEVANCE_MODEL
    
    prompt = (
        f"You are an editor filtering news for the client '{client_name}'.\n\n"
        f"{context_str}"
        f"Target Keywords/Topics: {', '.join(keywords)}\n\n"
        f"Article Title: {title}\n"
        f"Article Content: {body[:5000]}\n\n"
        f"Determine if this article is relevant to '{client_name}' based on the context, guidelines, and target keywords.\n"
        f"RELEVANCE RULES:\n"
        f"1. Return 'relevant' ONLY if the article is clearly on-topic for the client's described sections and would be genuinely useful to the client's teams.\n"
        f"2. Return 'not_relevant' if the article is off-topic, only tangentially related, or not actionable/useful for the client.\n"
        f"3. Return 'uncertain' ONLY for genuinely borderline cases — not as a default for weak or indirect matches.\n\n"
        f"You MUST output strictly in JSON format. Do not write any explanations outside the JSON structure. Response format:\n"
        f'{{"verdict": "relevant" | "not_relevant" | "uncertain", "reason": "concise explanation", "score": float between 0.0 and 1.0}}'
    )

    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": "You are a strict JSON classifier. You must return a raw JSON object and absolutely nothing else. Do not wrap the JSON in markdown code blocks (such as ```json ... ```), do not write any introductory or concluding text, and do not explain your choice. Output valid JSON matching the schema."
            },
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 400,
        "temperature": 0.0
    }
    
    with httpx.Client(timeout=15) as client:
        for attempt in range(2):
            api_key = random.choice(GROQ_API_KEYS)
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            try:
                resp = client.post(url, headers=headers, json=payload, timeout=12)
                if resp.status_code == 200:
                    ans = resp.json()["choices"][0]["message"]["content"].strip()
                    try:
                        data = safe_json_parse(ans)
                        verdict = str(data.get("verdict", "uncertain")).lower().strip()
                        reason = str(data.get("reason", "No reason provided"))
                        score = float(data.get("score", 0.5))
                        return verdict, reason, score
                    except Exception as json_err:
                        log(f"HTTP fallback relevance JSON parse error: {json_err}. Raw: {ans}")
                        ans_upper = ans.upper()
                        if "NOT_RELEVANT" in ans_upper:
                            return "not_relevant", "HTTP Fallback Regex not_relevant", 0.1
                        elif "RELEVANT" in ans_upper:
                            return "relevant", "HTTP Fallback Regex relevant", 0.9
                        return "uncertain", "HTTP Fallback JSON parse failure", 0.5
            except Exception as e:
                log(f"Relevance Fallback Groq check exception: {e}")
                
    return "uncertain", "HTTP fetch failed", 0.5

def check_relevance_with_groq(title: str, body: str, keywords: List[str], client_name: str, client_context: Optional[str] = None) -> tuple[bool, str, str, float]:
    """
    Asymmetric relevance evaluator with two-stage ensembling.
    Returns: (is_relevant: bool, verdict: str, reason: str, score: float)
    """
    verdict = "uncertain"
    reason = ""
    score = 0.5
    
    # --- STAGE 1: Primary Model (70B) ---
    try:
        verdict, reason, score = check_relevance_with_groq_oss(title, body, keywords, client_name, client_context, use_120b=False)
    except Exception as e:
        log(f"Primary relevance check (Groq SDK) failed: {e}. Trying HTTP fallback...")
        try:
            verdict, reason, score = check_relevance_with_groq_fallback_http(title, body, keywords, client_name, client_context, use_120b=False)
        except Exception as e2:
            log(f"Primary fallback HTTP check failed: {e2}")
            verdict = "uncertain"
            reason = f"Stage 1 exception: {e2}"
            
    # --- STAGE 2: Ensemble Check for borderlines / errors (120B) ---
    if verdict == "uncertain":
        log(f"Borderline / uncertain relevance detected for '{title}'. Escalating to secondary model (gpt-oss-120b)...")
        try:
            v_esc, r_esc, s_esc = check_relevance_with_groq_oss(title, body, keywords, client_name, client_context, use_120b=True)
            log(f"Ensemble response for '{title}': verdict={v_esc}, score={s_esc}")
            # Stage-2 is the arbiter: only explicit "relevant" keeps the article.
            if v_esc == "relevant":
                verdict = v_esc
                reason = f"Ensembled (120b confirmed relevant. Reason: {r_esc})"
                score = s_esc
            else:
                verdict = "not_relevant"
                reason = f"Ensembled (120b verdict: {v_esc}. Reason: {r_esc})"
                score = s_esc
        except Exception as e_esc:
            log(f"Ensemble check failed: {e_esc}. Defaulting to keep (bias toward recall).")
            # If both fail, bias toward keep
            return True, "uncertain", f"Ensemble failed: {e_esc}", 0.5
            
    is_relevant = (verdict == "relevant")
    return is_relevant, verdict, reason, score

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

def extract_metadata_with_groq_sync(body: str, url: str = "", context_agency: str = "", author_metadata: Dict = None, html_snippets: Dict = None) -> Dict[str, Any]:
    if not body or len(body) < 100: return {"author": None, "agency": context_agency or None, "body": body}
    domain = get_domain_name(url) if url else ""
    
    # State-of-the-Art "Judge" Prompt
    prompt = (
        f"Analyze this news article and extract metadata in JSON format.\n"
        f"Target Fields: author (specific person or null), handle (social media or null), agency (news org or null).\n\n"
        f"STAGED EVIDENCE:\n"
        f"1. HTML Metadata Extraction Suggestion: {author_metadata.get('name') if author_metadata else 'None'}\n"
        f"2. Suggested Handle: {author_metadata.get('handle') if author_metadata else 'None'}\n"
        f"3. HTML HEAD SNIPPET: {html_snippets.get('head') if html_snippets else 'None'}\n"
        f"4. BYLINE AREA SNIPPET: {html_snippets.get('top') if html_snippets else 'None'}\n\n"
        f"TASK: Use the snippets to verify or find the correct author. "
        f"If the metadata suggestion is generic (like 'Staff'), find the real name in the snippets. "
        f"If a specific handle is found, use it to confirm the author.\n\n"
        f"Text Sample: {body[:4000]}\n\n"
        f"You MUST output strictly in JSON format. Do not write any explanations outside the JSON structure. Response format:\n"
        f'{{"author": "string or null", "handle": "string or null", "agency": "string or null"}}'
    )
    
    api_key = os.getenv("GROQ_RELEVANCE_API_KEY")
    is_placeholder = not api_key or "ReplaceMe" in api_key or "your_groq" in api_key.lower()
    if is_placeholder:
        api_key = GROQ_API_KEYS[0] if GROQ_API_KEYS else None
        is_placeholder = not api_key
        
    model_name = GROQ_PRIMARY_MODEL
    
    if api_key:
        try:
            from groq import Groq
            client = Groq(api_key=api_key)
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a strict JSON extractor. You must return a raw JSON object and absolutely nothing else. Do not wrap the JSON in markdown code blocks (such as ```json ... ```), do not write any introductory or concluding text, and do not explain your choice. Output valid JSON matching the schema."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                max_completion_tokens=400,
                response_format={"type": "json_object"},
                top_p=1.0,
                stop=None
            )
            ans = completion.choices[0].message.content.strip()
            data = safe_json_parse(ans)
            res_agency = data.get("agency")
            if not res_agency or res_agency.lower() in ["google", "google news"]:
                 res_agency = context_agency or domain
            return {
                "author": data.get("author") or (author_metadata or {}).get("name"), 
                "handle": data.get("handle") or (author_metadata or {}).get("handle"),
                "agency": res_agency, 
                "is_junk": data.get("is_junk", False), 
                "cleaned_body": data.get("cleaned_body", body)
            }
        except Exception as e:
            log(f"Groq SDK Metadata Extraction error: {e}. Trying HTTP fallback...")

    if GROQ_API_KEYS and not is_placeholder:
        url_api = "https://api.groq.com/openai/v1/chat/completions"
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a strict JSON extractor. You must return a raw JSON object and absolutely nothing else. Do not wrap the JSON in markdown code blocks (such as ```json ... ```), do not write any introductory or concluding text, and do not explain your choice. Output valid JSON matching the schema."
                },
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 400,
            "temperature": 0.0
        }
        with httpx.Client(timeout=15) as client:
            for attempt in range(2):
                key = random.choice(GROQ_API_KEYS)
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                try:
                    resp = client.post(url_api, headers=headers, json=payload, timeout=12)
                    if resp.status_code == 200:
                        ans = resp.json()["choices"][0]["message"]["content"].strip()
                        data = safe_json_parse(ans)
                        res_agency = data.get("agency")
                        if not res_agency or res_agency.lower() in ["google", "google news"]:
                             res_agency = context_agency or domain
                        return {
                            "author": data.get("author") or (author_metadata or {}).get("name"), 
                            "handle": data.get("handle") or (author_metadata or {}).get("handle"),
                            "agency": res_agency, 
                            "is_junk": data.get("is_junk", False), 
                            "cleaned_body": data.get("cleaned_body", body)
                        }
                except Exception as e2:
                    log(f"Groq HTTP Fallback Metadata Extraction exception: {e2}")

    log("Groq Metadata Extraction failed completely. Falling back to local parsed suggestions.")
    return {"author": (author_metadata or {}).get("name"), "agency": context_agency or domain, "body": body}

def perform_full_enrichment_sync(body: str, title: str, url: str, sector: str, context_agency: str = "", extra_metadata: Dict = None, summary_length: int = 35) -> Dict[str, Any]:
    results = {"summary": None, "author": None, "agency": None, "tags": None, "sentiment": "neutral"}
    if not body or len(body) < 100: return results
    
    extra_metadata = extra_metadata or {}
    author_metadata = extra_metadata.get("author_metadata")
    html_snippets = extra_metadata.get("html_snippets")
    
    meta = extract_metadata_with_groq_sync(
        body, 
        url=url, 
        context_agency=context_agency, 
        author_metadata=author_metadata,
        html_snippets=html_snippets
    )
    
    results["author"] = meta.get("author")
    if meta.get("handle"):
        results["author"] = f"{results['author']} (@{meta['handle']})" if results["author"] else f"@{meta['handle']}"
    
    results["agency"] = meta.get("agency")
    results["summary"] = summarize_with_groq_sync(body, title=title, summary_length=summary_length)
    
    # Simple sentiment checks (Separate checks to avoid elution)
    body_low = body.lower()[:1000]
    if any(w in body_low for w in ["positive", "success", "breakthrough", "growth"]): 
        results["sentiment"] = "positive"
    if any(w in body_low for w in ["warning", "risk", "lawsuit", "antitrust", "failure"]): 
        results["sentiment"] = "negative"
    
    return results
