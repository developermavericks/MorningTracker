from scraper.search_utils import match_publication_category

def test_match_publication_category_a():
    # Category A checks by name and url
    assert match_publication_category("Reuters", "https://reuters.com/news/1") == "A"
    assert match_publication_category("Bloomberg News", "https://bloomberg.com/business") == "A"
    assert match_publication_category("The Times of India", "https://timesofindia.indiatimes.com/india") == "A"
    assert match_publication_category("ET Prime", "https://prime.economictimes.indiatimes.com/story") == "A"
    assert match_publication_category("Moneycontrol", "https://moneycontrol.com/news") == "A"
    assert match_publication_category("The Ken", "https://the-ken.com/article1") == "A"
    assert match_publication_category("Indulge (The New Indian Express)", "https://indulgeexpress.com/life") == "A"

def test_match_publication_category_b():
    # Category B checks by name and url
    assert match_publication_category("The New Indian Express", "https://newindianexpress.com/nation") == "B"
    assert match_publication_category("Deccan Herald", "https://deccanherald.com/opinion") == "B"
    assert match_publication_category("The Tribune", "https://tribuneindia.com/news") == "B"
    assert match_publication_category("Travel Daily Media", "https://traveldailymedia.com/news") == "B"
    assert match_publication_category("Live From A Lounge", "https://livefromalounge.com/deal") == "B"

def test_match_publication_category_c_and_unmapped():
    # Category C and unmapped checks
    assert match_publication_category("Millennium Post", "https://millenniumpost.in") == "C"
    assert match_publication_category("Unknown Blog", "https://myblog.com/post") == "C"

def test_match_publication_category_excluded_bc():
    # Excluded B/C publications must map to C
    assert match_publication_category("Money9", "https://money9.com") == "C"
    assert match_publication_category("Free Press Journal", "https://freepressjournal.in") == "C"
    assert match_publication_category("SME Street", "https://smestreet.in") == "C"
