from scraper.similarity import tokenize, calculate_cosine_similarity, evaluate_similarity_pre_filter, SIM_DROP_THRESHOLD

def test_tokenize():
    text = "Hello, Scapia's travel credit card!"
    tokens = tokenize(text)
    assert "hello" in tokens
    assert "scapia" in tokens
    assert "s" in tokens or "scapia" in tokens
    assert "travel" in tokens

def test_calculate_cosine_similarity():
    text1 = "Scapia co-branded travel credit card"
    text2 = "Scapia credit card"
    sim = calculate_cosine_similarity(text1, text2)
    assert sim > 0.5
    
    text3 = "completely unrelated text query"
    sim_low = calculate_cosine_similarity(text1, text3)
    assert sim_low < 0.1

def test_evaluate_similarity_pre_filter():
    title = "Scapia launches co-branded credit card with Federal Bank"
    body = "Travel fintech startup Scapia has partnerned with Federal Bank to offer co-branded travel credit cards to users with zero forex markup."
    keywords = ["Scapia", "credit card", "travel"]
    client_context = "Scapia travel fintech co-branded credit cards Anil Goteti"
    
    score = evaluate_similarity_pre_filter(title, body, keywords, client_context)
    assert score > SIM_DROP_THRESHOLD
    
    title_unrelated = "Local farmer grows giant pumpkin in backyard"
    body_unrelated = "An extraordinary agricultural feat took place in a remote village where a massive pumpkin weighing over 500 kilograms was harvested."
    score_unrelated = evaluate_similarity_pre_filter(title_unrelated, body_unrelated, keywords, client_context)
    assert score_unrelated < SIM_DROP_THRESHOLD

def test_keyword_classification():
    from scraper.engine import is_generic_keyword, quote_keyword
    assert is_generic_keyword("UPI") is True
    assert is_generic_keyword("startups India") is True
    assert is_generic_keyword("Scapia") is False
    assert is_generic_keyword("Federal Bank India") is False
    
    assert quote_keyword("OneCard") == '"OneCard"'
    assert quote_keyword('"AlreadyQuoted"') == '"AlreadyQuoted"'

