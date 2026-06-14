from scraper.tasks import should_use_playwright

def test_should_use_playwright():
    # Known hostile domains should return True
    assert should_use_playwright("https://axios.com") is True
    assert should_use_playwright("https://www.axios.com/some-article") is True
    assert should_use_playwright("https://ndtv.com") is True
    assert should_use_playwright("https://special.ndtv.com/news") is True
    
    # Regular domains should return False
    assert should_use_playwright("https://google.com") is False
    assert should_use_playwright("https://www.livemint.com/news") is False
