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

def match_publication_category(agency_name: str, url: str) -> str:
    """
    Categorizes the publication of an article into 'A', 'B', or 'C'
    based on the agency name or domain URL.
    """
    name_to_check = (agency_name or "").strip().lower()
    url_to_check = (url or "").strip().lower()
    
    # Category A Patterns
    category_a_regexes = [
        re.compile(p, re.IGNORECASE) for p in [
            r"reuters\.com", r"\breuters\b",
            r"bloomberg\.com", r"\bbloomberg\b",
            r"timesofindia", r"times of india", r"delhitimes", r"delhi times", r"mumbaitimes", r"mumbai times", r"bombaytimes", r"bombay times",
            r"hindustantimes", r"hindustan times", r"ht brunch", r"htbrunch",
            r"\bindianexpress\.com", r"(?<!new\s)indian express",
            r"thehindu\.com", r"the hindu",
            r"economictimes", r"economic times", r"et now", r"etnow", r"et prime", r"etprime", r"et wealth", r"etwealth", r"ettravelworld", r"et travelworld", r"ethospitalityworld", r"et hospitalityworld",
            r"indiatoday", r"india today",
            r"zeenews", r"zee news",
            r"news18",
            r"zeebiz", r"zee business",
            r"cnbctv18", r"cnbc tv18",
            r"moneycontrol",
            r"livemint", r"\bmint\b", r"mint lounge", r"mintlounge",
            r"business-standard", r"business standard",
            r"financialexpress", r"financial express",
            r"thehindubusinessline", r"business line", r"businessline",
            r"forbesindia", r"forbes india",
            r"fortuneindia", r"fortune india",
            r"businesstoday", r"business today",
            r"theweek\.in", r"\bthe week\b",
            r"outlookmoney", r"outlook money",
            r"pti\.in", r"\bpti\b", r"press trust of india",
            r"cntraveller", r"condé nast", r"conde nast",
            r"natgeotraveller", r"national geographic",
            r"travelandleisureindia", r"travel \+ leisure", r"travel and leisure",
            r"curlytales", r"curly tales",
            r"outlooktraveller", r"outlook traveller",
            r"skift",
            r"the-ken\.com", r"the ken",
            r"yourstory",
            r"inc42",
            r"vccircle",
            r"harpersbazaar", r"harper’s bazaar", r"harper's bazaar",
            r"story18",
            r"peoplematters", r"people matters",
            r"ians\.in", r"\bians\b",
            r"indulgeexpress", r"indulge \(the new indian express\)", r"indulge",
            r"autocar", r"bike india", r"bikeindia", r"overdrive", r"powerdrift", r"zigwheels"
        ]
    ]

    # Category B Patterns
    category_b_regexes = [
        re.compile(p, re.IGNORECASE) for p in [
            r"newindianexpress", r"new indian express",
            r"deccanherald", r"deccan herald",
            r"tribuneindia", r"the tribune",
            r"telegraphindia", r"the telegraph",
            r"deccanchronicle", r"deccan chronicle",
            r"news9live", r"news9",
            r"travelandtourworld", r"travel & tour world", r"travel and tour world",
            r"traveldailymedia", r"travel daily",
            r"travelbizmonitor", r"travel biz monitor",
            r"hotelierindia", r"hotelier india",
            r"bwhotelier", r"bw hotelier",
            r"indianretailer", r"indian retailer",
            r"tradebrains", r"trade brains",
            r"livefromalounge", r"live from a lounge",
            r"traveltrendstoday", r"travel trends today",
            r"bottindia",
            r"hospitalitybizindia", r"hospitality biz",
            r"ttrweekly", r"ttr weekly",
            r"bweverythingexperiential", r"bw everything experiential",
            r"heraldgoa", r"oheraldo", r"goan herald", r"herald",
            r"uniindia", r"united news of india", r"\buni\b",
            r"thehansindia", r"the hans india"
        ]
    ]

    # Check Category A
    for regex in category_a_regexes:
        if regex.search(name_to_check) or regex.search(url_to_check):
            return "A"

    # Check Category B
    for regex in category_b_regexes:
        if regex.search(name_to_check) or regex.search(url_to_check):
            return "B"

    # Default to C
    return "C"
