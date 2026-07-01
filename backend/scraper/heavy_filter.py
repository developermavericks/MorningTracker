"""
Heavy Automation filtering pipeline.

Implements a 4-stage funnel:
  Stage 1 — Normalize + exact dedup (SHA-256 of normalized title)
  Stage 2 — Near-dup clustering (TF-IDF cosine, threshold 0.80)
  Stage 3 — 592-keyword Aho-Corasick match + 16 boolean rules + guard logic
  Stage 4 — Relevance scoring → bucket into clear_keep / ambiguous_middle / clear_discard

Stage 4 LLM pass (ambiguous_middle only) is handled in the Celery task to keep
this module dependency-free of heavy imports.
"""

import csv
import hashlib
import json
import logging
import os
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_KEYWORDS_CSV = os.path.join(_DATA_DIR, "keywords_clean.csv")
_BOOLEAN_CSV  = os.path.join(_DATA_DIR, "boolean_rules.csv")

# ── Guard signals: articles must contain one of these to pass guarded keywords ─

_INDIA_SIGNALS  = ["india", "indian", "bharat", "delhi", "mumbai", "bengaluru", "bangalore", "hyderabad", "chennai", "kolkata"]
_GOOGLE_SIGNALS = ["google", "alphabet", "sundar pichai", "google india", "google llc"]


# ── Text normalisation ────────────────────────────────────────────────────────

def normalize_text(text: str) -> str:
    """Lowercase, strip HTML tags, collapse whitespace."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def title_hash(title: str) -> str:
    norm = normalize_text(title)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


# ── Stage 1 — Exact dedup ────────────────────────────────────────────────────

def exact_dedup(articles: List[dict]) -> List[dict]:
    """
    Drop articles with duplicate normalized titles.
    Returns deduplicated list; first occurrence wins.
    """
    seen: set = set()
    result = []
    for art in articles:
        h = title_hash(art.get("title", ""))
        if h not in seen:
            seen.add(h)
            result.append(art)
    return result


# ── Stage 2 — Near-dup clustering (TF-IDF cosine) ────────────────────────────

def near_dedup(articles: List[dict], threshold: float = 0.80) -> List[dict]:
    """
    Cluster near-duplicate articles (same story, different outlets) using
    TF-IDF cosine similarity. Keeps the representative with the longest body.
    Attaches 'cluster_outlets' to each kept article.
    """
    if len(articles) <= 1:
        return articles

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np

        texts = [
            normalize_text((a.get("title") or "") + " " + (a.get("full_body") or a.get("summary") or ""))
            for a in articles
        ]

        vec = TfidfVectorizer(max_features=5000, sublinear_tf=True)
        tfidf = vec.fit_transform(texts)
        sim = cosine_similarity(tfidf)

        # Union-Find clustering
        parent = list(range(len(articles)))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        n = len(articles)
        for i in range(n):
            for j in range(i + 1, n):
                if sim[i, j] >= threshold:
                    union(i, j)

        # Group by cluster root
        clusters: Dict[int, List[int]] = {}
        for idx in range(n):
            root = find(idx)
            clusters.setdefault(root, []).append(idx)

        result = []
        for indices in clusters.values():
            # Pick representative: longest body
            best = max(indices, key=lambda i: len(articles[i].get("full_body") or articles[i].get("summary") or ""))
            rep = dict(articles[best])
            outlets = list({
                articles[i].get("agency") or articles[i].get("source_feed") or "Unknown"
                for i in indices
                if i != best
            })
            rep["cluster_outlets"] = outlets
            rep["cluster_size"] = len(indices)
            result.append(rep)

        logger.info(f"Near-dedup: {len(articles)} → {len(result)} articles after clustering")
        return result

    except Exception as e:
        logger.warning(f"Near-dedup failed, skipping: {e}")
        return articles


# ── Stage 3A — Keyword matcher ────────────────────────────────────────────────

class KeywordMatcher:
    """
    Loads keywords_clean.csv and provides fast multi-keyword matching.
    Uses flashtext KeywordProcessor for Aho-Corasick speed.
    """

    def __init__(self):
        self._keywords: List[dict] = []
        self._processor = None
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        try:
            from flashtext import KeywordProcessor
            kp = KeywordProcessor(case_sensitive=False)
            with open(_KEYWORDS_CSV, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    kw = row.get("Keyword", "").strip()
                    if not kw:
                        continue
                    meta = {
                        "keyword":    kw,
                        "pillar":     row.get("Pillar", "").strip(),
                        "subcategory":row.get("Subcategory", "").strip(),
                        "role":       row.get("Role", "").strip(),
                        "match_type": row.get("Match Type", "exact").strip(),
                        "needs_guard":row.get("Needs Guard", "").strip().upper() in ("YES", "Y"),
                    }
                    self._keywords.append(meta)
                    kp.add_keyword(kw, meta)
            self._processor = kp
            self._loaded = True
            logger.info(f"KeywordMatcher loaded {len(self._keywords)} keywords")
        except Exception as e:
            logger.error(f"KeywordMatcher load failed: {e}")
            self._loaded = True  # don't retry

    def match(self, title: str, body: str) -> List[dict]:
        """
        Returns list of keyword hit dicts with 'keyword', 'pillar', 'subcategory',
        'role', 'needs_guard', 'in_title' fields.
        """
        self._load()
        if not self._processor:
            return []

        hits = []
        norm_title = normalize_text(title)
        norm_body  = normalize_text(body)

        title_hits = self._processor.extract_keywords(norm_title, span_info=False)
        body_hits  = self._processor.extract_keywords(norm_body,  span_info=False)

        seen = set()
        for hit in title_hits:
            if isinstance(hit, dict) and hit.get("keyword") not in seen:
                seen.add(hit["keyword"])
                hits.append({**hit, "in_title": True})
        for hit in body_hits:
            if isinstance(hit, dict) and hit.get("keyword") not in seen:
                seen.add(hit["keyword"])
                hits.append({**hit, "in_title": False})

        return hits


# Singleton — loaded once per worker process
_keyword_matcher = KeywordMatcher()


def apply_guard_filter(hits: List[dict], full_text: str) -> List[dict]:
    """
    Drops hits flagged 'needs_guard=True' if the article text contains no
    Google/India co-occurrence signal.
    """
    text_lower = full_text.lower()
    has_google = any(s in text_lower for s in _GOOGLE_SIGNALS)
    has_india  = any(s in text_lower for s in _INDIA_SIGNALS)
    has_signal = has_google or has_india

    result = []
    for h in hits:
        if h.get("needs_guard") and not has_signal:
            continue
        result.append(h)
    return result


# ── Stage 3B — Boolean rule evaluator ────────────────────────────────────────

class BooleanRuleEvaluator:
    """
    Loads boolean_rules.csv and evaluates each rule against article text.
    Supports: AND, OR, NEAR/N (proximity), quoted phrases.
    Each comma-separated sub-expression is an OR alternative.
    """

    def __init__(self):
        self._rules: List[dict] = []
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        try:
            with open(_BOOLEAN_CSV, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self._rules.append({
                        "pillar":     row.get("Pillar", "").strip(),
                        "subcategory":row.get("Subcategory", "").strip(),
                        "rule":       row.get("Boolean Rule", "").strip(),
                    })
            self._loaded = True
            logger.info(f"BooleanRuleEvaluator loaded {len(self._rules)} rules")
        except Exception as e:
            logger.error(f"BooleanRuleEvaluator load failed: {e}")
            self._loaded = True

    @staticmethod
    def _extract_phrases(text: str) -> List[str]:
        """Extract all quoted phrases from a rule fragment."""
        return re.findall(r'"([^"]+)"', text)

    @staticmethod
    def _near_n_check(text: str, term_a: str, term_b: str, n: int) -> bool:
        """Check if term_a and term_b appear within n words of each other."""
        words = text.lower().split()
        positions_a = [i for i, w in enumerate(words) if term_a.lower() in w]
        positions_b = [i for i, w in enumerate(words) if term_b.lower() in w]
        return any(abs(pa - pb) <= n for pa in positions_a for pb in positions_b)

    def _eval_fragment(self, fragment: str, text: str) -> bool:
        """Evaluate a single boolean sub-expression against lowercased text."""
        fragment = fragment.strip().strip("()")
        text_lower = text.lower()

        # Handle NEAR/N: e.g. "CCI" NEAR/5 "India"
        near_match = re.search(r'"([^"]+)"\s+NEAR/(\d+)\s+"([^"]+)"', fragment, re.IGNORECASE)
        if near_match:
            term_a = near_match.group(1)
            n      = int(near_match.group(2))
            term_b = near_match.group(3)
            if not self._near_n_check(text_lower, term_a, term_b, n):
                return False
            # Remove the NEAR clause and evaluate remaining AND/OR parts
            fragment = re.sub(r'"[^"]+"\s+NEAR/\d+\s+"[^"]+"', "", fragment, flags=re.IGNORECASE).strip()
            if not fragment.strip().strip("()").strip():
                return True

        # Handle AND
        if " AND " in fragment.upper():
            parts = re.split(r'\bAND\b', fragment, flags=re.IGNORECASE)
            return all(self._eval_fragment(p, text_lower) for p in parts)

        # Handle OR
        if " OR " in fragment.upper():
            parts = re.split(r'\bOR\b', fragment, flags=re.IGNORECASE)
            return any(self._eval_fragment(p, text_lower) for p in parts)

        # Bare quoted phrase — check presence
        phrases = self._extract_phrases(fragment)
        if phrases:
            return all(p.lower() in text_lower for p in phrases)

        # Unquoted term
        term = fragment.strip().strip('"').lower()
        return bool(term) and term in text_lower

    def evaluate(self, text: str) -> List[dict]:
        """
        Returns list of matched rules: {pillar, subcategory}.
        Comma-separated alternatives are OR-ed.
        """
        self._load()
        matched = []
        text_lower = text.lower()

        for rule in self._rules:
            rule_text = rule["rule"]
            # Split on top-level commas (comma = OR between sub-expressions)
            # Simple split — handles most rules adequately
            alternatives = [a.strip() for a in rule_text.split(",") if a.strip()]
            if any(self._eval_fragment(alt, text_lower) for alt in alternatives):
                matched.append({"pillar": rule["pillar"], "subcategory": rule["subcategory"]})

        return matched


_boolean_evaluator = BooleanRuleEvaluator()


# ── Stage 4 — Relevance scoring ───────────────────────────────────────────────

# Role → base score weight
_ROLE_WEIGHTS = {
    "google":       {"title": 3.0, "body": 2.0},
    "brand_variant":{"title": 2.5, "body": 1.5},
    "competitor":   {"title": 1.5, "body": 1.0},
    "industry":     {"title": 0.5, "body": 0.3},
}

# Boolean rule hit always adds this to score
_BOOLEAN_RULE_BONUS = 4.0

# Maximum possible raw score (used to normalize to 0–1)
_MAX_SCORE = 12.0


def score_article(article: dict) -> Tuple[float, List[dict], Optional[str], Optional[str], str]:
    """
    Score a single article. Returns:
      (normalized_score 0–1, keyword_hits, pillar, sub_category, bucket)
    """
    title   = article.get("title", "") or ""
    body    = article.get("full_body") or article.get("summary") or ""
    full_text = title + " " + body

    # 3A — keyword hits
    raw_hits   = _keyword_matcher.match(title, body)
    clean_hits = apply_guard_filter(raw_hits, full_text)

    # 3B — boolean rules
    bool_matches = _boolean_evaluator.evaluate(full_text)

    # Score from keyword hits
    raw_score = 0.0
    seen_keywords = set()
    for h in clean_hits:
        kw = h.get("keyword", "")
        if kw in seen_keywords:
            continue
        seen_keywords.add(kw)
        role    = h.get("role", "industry")
        weights = _ROLE_WEIGHTS.get(role, _ROLE_WEIGHTS["industry"])
        if h.get("in_title"):
            raw_score += weights["title"]
        else:
            raw_score += weights["body"]

    # Bonus for boolean rule hit
    if bool_matches:
        raw_score += _BOOLEAN_RULE_BONUS

    # Normalize
    norm_score = min(raw_score / _MAX_SCORE, 1.0)

    # Determine pillar / subcategory
    # Boolean match takes priority (higher confidence)
    pillar     = None
    sub_cat    = None
    if bool_matches:
        pillar  = bool_matches[0]["pillar"]
        sub_cat = bool_matches[0]["subcategory"]
    elif clean_hits:
        # Pick pillar from highest-weight keyword hit
        google_hits = [h for h in clean_hits if h.get("role") == "google"]
        top_hit     = google_hits[0] if google_hits else clean_hits[0]
        pillar      = top_hit.get("pillar")
        sub_cat     = top_hit.get("subcategory")

    # Bucket: competitor with no Google hit → competitive-intel only (still kept)
    google_hits    = [h for h in clean_hits if h.get("role") in ("google", "brand_variant")]
    competitor_hits= [h for h in clean_hits if h.get("role") == "competitor"]

    return norm_score, clean_hits, pillar, sub_cat


def bucket_articles(
    articles: List[dict],
    threshold: float = 0.5,
    boolean_matches_map: Optional[Dict[int, bool]] = None,
) -> Tuple[List[dict], List[dict], List[dict]]:
    """
    Score all articles and split into three buckets.
    Returns (clear_keep, ambiguous_middle, clear_discard).
    """
    clear_keep       = []
    ambiguous_middle = []
    clear_discard    = []

    for art in articles:
        score, hits, pillar, sub_cat = score_article(art)

        art["_relevance_score"] = score
        art["_keyword_hits"]    = [h.get("keyword") for h in hits]
        art["_pillar"]          = pillar
        art["_sub_category"]    = sub_cat

        # Boolean rule hits always force into clear_keep
        bool_matches = _boolean_evaluator.evaluate(
            (art.get("title") or "") + " " + (art.get("full_body") or art.get("summary") or "")
        )
        art["_boolean_matched"] = bool(bool_matches)

        if bool_matches or score >= threshold:
            art["_bucket"] = "clear_keep"
            clear_keep.append(art)
        elif score >= threshold * 0.5 and hits:
            art["_bucket"] = "ambiguous_middle"
            ambiguous_middle.append(art)
        else:
            art["_bucket"] = "clear_discard"
            clear_discard.append(art)

    logger.info(
        f"Bucketing: keep={len(clear_keep)}, "
        f"ambiguous={len(ambiguous_middle)}, "
        f"discard={len(clear_discard)}"
    )
    return clear_keep, ambiguous_middle, clear_discard


# ── BM25 re-ranking (optional, for Hybrid method) ────────────────────────────

def bm25_rerank(articles: List[dict], query_terms: List[str], top_n: int = 200) -> List[dict]:
    """
    Re-rank articles using BM25 against query_terms.
    Returns top_n articles sorted by BM25 score descending.
    """
    if not articles or not query_terms:
        return articles
    try:
        from rank_bm25 import BM25Okapi

        corpus = [
            normalize_text(
                (a.get("title") or "") + " " + (a.get("full_body") or a.get("summary") or "")
            ).split()
            for a in articles
        ]
        bm25  = BM25Okapi(corpus)
        scores = bm25.get_scores(query_terms)

        ranked = sorted(zip(scores, articles), key=lambda x: x[0], reverse=True)
        return [a for _, a in ranked[:top_n]]
    except Exception as e:
        logger.warning(f"BM25 rerank failed: {e}")
        return articles
