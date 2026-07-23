from scraper.tasks import build_mailer_grouped_data

def test_pure_google_article():
    # A Google article with no competitor brands should be in the Google section
    articles = [
        {
            "title": "Google Gemini receives new coding features",
            "summary": "Google announces major updates to its generative AI assistant Gemini.",
            "_keyword_hits": ["gemini"]
        }
    ]
    grouped = build_mailer_grouped_data(articles)
    
    assert "Google" in grouped
    assert "AI Specific/Research" in grouped["Google"]
    assert len(grouped["Google"]["AI Specific/Research"]) == 1
    
    assert "Competition" not in grouped


def test_pure_samsung_article():
    # A Samsung article with no Google references should be in the Competition section
    articles = [
        {
            "title": "Samsung Galaxy Buds Pro launched in India",
            "summary": "Samsung released its latest wireless earbuds today.",
            "_keyword_hits": ["samsung galaxy buds"]
        }
    ]
    grouped = build_mailer_grouped_data(articles)
    
    assert "Competition" in grouped
    assert "Samsung" in grouped["Competition"]
    assert len(grouped["Competition"]["Samsung"]) == 1
    
    assert "Google" not in grouped


def test_overlapping_samsung_google_article():
    # An article mentioning both Samsung and Google Gemini should ONLY go into the Competition section
    articles = [
        {
            "title": "Samsung launches Galaxy S26 with integrated Google Gemini",
            "summary": "Samsung's newest flagship phone features deep Google Gemini integration.",
            "_keyword_hits": ["samsung galaxy india", "google india"]
        }
    ]
    grouped = build_mailer_grouped_data(articles)
    
    # It must be in Competition section
    assert "Competition" in grouped
    assert "Samsung" in grouped["Competition"]
    assert len(grouped["Competition"]["Samsung"]) == 1
    
    # It must NOT be in the Google section (as requested: only direct Google news in Google section)
    assert "Google" not in grouped or not any(grouped["Google"].values())


def test_google_crisis_article():
    # A Google crisis article should be under Google's Critical/Crisis, NOT Competition's Crisis Related
    articles = [
        {
            "title": "CCI penalizes Google over Play Store policies",
            "summary": "The Competition Commission of India has imposed a fine on Google.",
            "_keyword_hits": ["google india"]
        }
    ]
    grouped = build_mailer_grouped_data(articles)
    
    assert "Google" in grouped
    assert "Critical/Crisis" in grouped["Google"]
    assert len(grouped["Google"]["Critical/Crisis"]) == 1
    
    # It must NOT be in the Competition section's Crisis Related
    if "Competition" in grouped:
        assert "Crisis Related" not in grouped["Competition"] or len(grouped["Competition"]["Crisis Related"]) == 0


def test_competitor_crisis_article():
    # A competitor crisis article should go to both the competitor brand and the Competition Crisis Related
    articles = [
        {
            "title": "Apple faces penalty for anti-competitive App Store rules",
            "summary": "Regulators have imposed a penalty on Apple for its App Store practices.",
            "_keyword_hits": ["apple"]
        }
    ]
    grouped = build_mailer_grouped_data(articles)
    
    assert "Competition" in grouped
    assert "Apple" in grouped["Competition"]
    assert len(grouped["Competition"]["Apple"]) == 1
    assert "Crisis Related" in grouped["Competition"]
    assert len(grouped["Competition"]["Crisis Related"]) == 1
    
    assert "Google" not in grouped or not any(grouped["Google"].values())
