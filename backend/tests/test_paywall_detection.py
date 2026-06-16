"""Tests for the paywall detection utility function."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper.tasks import detect_paywall, KNOWN_PAYWALLED_DOMAINS


def test_known_domain_detection():
    """Articles from known paywalled domains should be detected."""
    assert detect_paywall("https://the-ken.com/story/fintech-slice-123", "", "") is True
    assert detect_paywall("https://www.livemint.com/companies/news/article", "", "") is True
    assert detect_paywall("https://economictimes.indiatimes.com/tech/startups/story", "", "") is True
    assert detect_paywall("https://www.business-standard.com/article/companies", "", "") is True
    assert detect_paywall("https://www.ft.com/content/some-article", "", "") is True


def test_unknown_domain_no_paywall():
    """Articles from non-paywalled sites with full body text should NOT be flagged."""
    long_body = "This is a complete article about fintech innovations in India. " * 20
    assert detect_paywall("https://techcrunch.com/2026/article", "<html><body>Full content</body></html>", long_body) is False
    assert detect_paywall("https://yourstory.com/2026/some-startup", "<html><body>Content</body></html>", long_body) is False


def test_html_heuristic_detection():
    """Articles with paywall CSS classes or phrases in HTML should be detected."""
    paywall_html_class = '<div class="paywall-container"><p>Subscribe to continue reading</p></div>'
    assert detect_paywall("https://example.com/article", paywall_html_class, "") is True
    
    paywall_html_text = '<div><p>This is a premium article. You have reached your free article limit.</p></div>'
    assert detect_paywall("https://example.com/article", paywall_html_text, "") is True
    
    paywall_subscribe = '<div class="gate"><p>Sign up to read this article</p></div>'
    assert detect_paywall("https://example.com/article", paywall_subscribe, "") is True


def test_short_body_with_large_html():
    """Short extracted text from a large HTML page indicates paywall truncation."""
    large_html = "<html>" + "x" * 6000 + "</html>"
    short_body = "Short teaser text"
    assert detect_paywall("https://example.com/article", large_html, short_body) is True


def test_no_paywall_with_full_content():
    """Normal articles with full content should NOT be flagged as paywalled."""
    normal_html = "<html><body>" + "Content " * 100 + "</body></html>"
    full_body = "This is a complete news article about technology. " * 30
    assert detect_paywall("https://ndtv.com/tech/article", normal_html, full_body) is False


def test_known_paywalled_domains_set_is_populated():
    """Verify that the known paywalled domains set contains expected entries."""
    assert "the-ken.com" in KNOWN_PAYWALLED_DOMAINS
    assert "livemint.com" in KNOWN_PAYWALLED_DOMAINS
    assert "wsj.com" in KNOWN_PAYWALLED_DOMAINS
    assert len(KNOWN_PAYWALLED_DOMAINS) >= 5


def test_subdomain_matching():
    """Subdomains of known paywalled domains should also be detected."""
    assert detect_paywall("https://prime.economictimes.indiatimes.com/article", "", "") is True
    assert detect_paywall("https://premium.ft.com/content/article", "", "") is True
