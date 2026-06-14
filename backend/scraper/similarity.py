import re
import math
from collections import Counter
from typing import List

# Similarity Thresholds
SIM_DROP_THRESHOLD = 0.02
SIM_PASS_THRESHOLD = 0.12

def tokenize(text: str) -> List[str]:
    """Lowercase and extract word tokens."""
    if not text:
        return []
    return re.findall(r'\b\w+\b', text.lower())

def calculate_cosine_similarity(text1: str, text2: str) -> float:
    """Computes cosine similarity of word frequencies between two texts."""
    tokens1 = tokenize(text1)
    tokens2 = tokenize(text2)
    
    if not tokens1 or not tokens2:
        return 0.0
        
    vec1 = Counter(tokens1)
    vec2 = Counter(tokens2)
    
    intersection = set(vec1.keys()) & set(vec2.keys())
    numerator = sum(vec1[word] * vec2[word] for word in intersection)
    
    sum1 = sum(count ** 2 for count in vec1.values())
    sum2 = sum(count ** 2 for count in vec2.values())
    
    denominator = math.sqrt(sum1) * math.sqrt(sum2)
    if not denominator:
        return 0.0
        
    return float(numerator) / denominator

def evaluate_similarity_pre_filter(title: str, body: str, keywords: List[str], client_context: str = "") -> float:
    """
    Computes similarity between the article content and the brand profile.
    """
    # Build brand profile reference text
    profile_components = []
    if client_context:
        profile_components.append(client_context)
    if keywords:
        profile_components.append(" ".join(keywords))
    profile_text = " ".join(profile_components)
    
    # Build article reference text
    article_components = [title]
    if body:
        # Evaluate against first 3000 chars of body to be consistent and fast
        article_components.append(body[:3000])
    article_text = " ".join(article_components)
    
    return calculate_cosine_similarity(article_text, profile_text)
