import re
from typing import List, Dict

def parse_boolean_query(query: str) -> Dict[str, List[str]]:
    """
    Parses a query string for boolean modifiers.
    Returns a dict with:
    - 'must': list of keywords that MUST be present
    - 'not': list of keywords that MUST NOT be present
    - 'should': list of keywords where at least one should be present (if 'must' is empty)
    """
    if not query:
        return {"must": [], "not": [], "should": []}

    # Split by spaces but respect phrases in quotes? 
    # For now, let's keep it simple as requested: + and -
    
    # regex to find +word, -word, or just word
    # handles "+word", "-word", "word"
    # also handles multi-word if we wanted, but let's stick to user example
    tokens = re.findall(r'([+-]?[\w\d]+)', query)
    
    must = []
    excluded = []
    should = []
    
    for token in tokens:
        if token.startswith('+'):
            must.append(token[1:].lower())
        elif token.startswith('-'):
            excluded.append(token[1:].lower())
        else:
            should.append(token.lower())
            
    return {
        "must": must,
        "not": excluded,
        "should": should
    }

def verify_boolean_relevance(text: str, segments: List[str]) -> bool:
    """
    Verifies if the text matches ANY of the comma-separated segments.
    Each segment can have boolean modifiers.
    """
    if not text or not segments:
        return True
        
    text_lower = text.lower()
    
    for segment in segments:
        parsed = parse_boolean_query(segment)
        
        # 1. Check MUST NOT (Exclude immediately if any forbidden word found)
        if any(bad in text_lower for bad in parsed["not"]):
            continue
            
        # 2. Check MUST (All mandatory words must be present)
        if parsed["must"]:
            if all(good in text_lower for good in parsed["must"]):
                # If there are 'should' words in this same segment, one of them must also match
                # unless they are just part of the phrase.
                # Usually, if we have "A + B", A is should, +B is must.
                # So we check if ANY "should" matches + ALL "must" matches.
                if not parsed["should"] or any(s in text_lower for s in parsed["should"]):
                    return True
        else:
            # No MUST words, just check if ANY 'should' word matches
            if any(s in text_lower for s in parsed["should"]):
                return True
                
    return False
