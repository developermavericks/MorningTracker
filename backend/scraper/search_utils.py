import re
from typing import List, Dict

def parse_boolean_query(query: str) -> Dict[str, List[str]]:
    """
    Parses a query string for boolean modifiers.
    If the query does not contain start-of-term modifiers (+ or -),
    it is treated as a single literal phrase to preserve hyphens, dots, and spaces.
    """
    if not query:
        return {"must": [], "not": [], "should": []}

    query = query.strip()

    # Determine if it's a boolean query (contains + or - at start of a term)
    is_boolean = False
    if query.startswith('+') or query.startswith('-'):
        is_boolean = True
    elif re.search(r'\s[+-]', query):
        is_boolean = True

    if not is_boolean:
        # Literal phrase matching
        return {
            "must": [],
            "not": [],
            "should": [query.lower()]
        }

    # Split by spaces but respect phrases
    tokens = query.split()
    
    must = []
    excluded = []
    should = []
    
    for token in tokens:
        token = token.strip("'\"")
        if not token:
            continue
        if token.startswith('+') and len(token) > 1:
            must.append(token[1:].lower())
        elif token.startswith('-') and len(token) > 1:
            excluded.append(token[1:].lower())
        else:
            should.append(token.lower())
            
    return {
        "must": must,
        "not": excluded,
        "should": should
    }

def match_keyword(text: str, kw: str) -> bool:
    """Matches a keyword/phrase in text ensuring proper word boundaries."""
    if not text or not kw:
        return False
    # Build pattern with word boundaries only where the keyword starts/ends with word characters
    pattern = ""
    if kw[0].isalnum() or kw[0] == '_':
        pattern += r"\b"
    pattern += re.escape(kw)
    if kw[-1].isalnum() or kw[-1] == '_':
        pattern += r"\b"
    return bool(re.search(pattern, text, re.IGNORECASE))

def verify_boolean_relevance(text: str, segments: List[str]) -> bool:
    """
    Verifies if the text matches ANY of the comma-separated segments.
    Each segment can have boolean modifiers.
    """
    if not text or not segments:
        return True
        
    for segment in segments:
        parsed = parse_boolean_query(segment)
        
        # 1. Check MUST NOT (Exclude immediately if any forbidden word found)
        if any(match_keyword(text, bad) for bad in parsed["not"]):
            continue
            
        # 2. Check MUST (All mandatory words must be present)
        if parsed["must"]:
            if all(match_keyword(text, good) for good in parsed["must"]):
                # If there are 'should' words in this same segment, one of them must also match
                if not parsed["should"] or any(match_keyword(text, s) for s in parsed["should"]):
                    return True
        else:
            # No MUST words, just check if ANY 'should' word matches
            if any(match_keyword(text, s) for s in parsed["should"]):
                return True
                
    return False

