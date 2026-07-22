import sys
import os
import unittest

# Add backend to sys.path to ensure local imports work
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from Pooja_filtering_Logic_for_heavy_automation_final.filter_priority_media import build_match_keywords, is_priority

class TestFilterPriorityMedia(unittest.TestCase):
    def test_known_aliases_spaceless(self):
        # We pass a mock list of publications that matches key names in known_aliases
        publications = [
            "ANI",
            "BloombergQuint",
            "Analytics India",
            "Business Standard",
            "Outlook India",
            "BW BusinessWorld",
            "Forbes India",
            "Fortune India",
            "Business Today",
            "Business India",
            "The Ken",
            "The Morning Context",
            "Deccan Herald",
            "Deccan Chronicle",
            "India Today",
            "ET BrandEquity",
            "Amar Ujala",
            "Dainik Bhaskar",
            "Bhaskar Hindi",
            "Bhaskar Live",
            "Dainik Jagran",
            "Navbharat Times",
            "DT Next",
            "Mumbai Mirror",
            "The Times of India",
            "Hindustan Times",
            "The New Indian Express",
            "The Tribune",
            "The Statesman",
            "The Telegraph",
            "The Indian Express",
            "The Economic Times"
        ]
        
        match_pairs = build_match_keywords(publications)
        
        # Test original names and aliases with spaces match correctly
        self.assertTrue(is_priority("ani news", match_pairs)[0])
        self.assertTrue(is_priority("ndtv profit", match_pairs)[0])
        self.assertTrue(is_priority("aim media house", match_pairs)[0])
        self.assertTrue(is_priority("the morning context", match_pairs)[0])
        self.assertTrue(is_priority("telegraph india", match_pairs)[0])
        
        # Test new spaceless aliases match correctly
        self.assertTrue(is_priority("aninews", match_pairs)[0])
        self.assertTrue(is_priority("ndtvprofit", match_pairs)[0])
        self.assertTrue(is_priority("analyticsindia", match_pairs)[0])
        self.assertTrue(is_priority("aimmediahouse", match_pairs)[0])
        self.assertTrue(is_priority("businessstandard", match_pairs)[0])
        self.assertTrue(is_priority("outlookindia", match_pairs)[0])
        self.assertTrue(is_priority("bwbusinessworld", match_pairs)[0])
        self.assertTrue(is_priority("bwbusiness", match_pairs)[0])
        self.assertTrue(is_priority("forbesindia", match_pairs)[0])
        self.assertTrue(is_priority("fortuneindia", match_pairs)[0])
        self.assertTrue(is_priority("businesstoday", match_pairs)[0])
        self.assertTrue(is_priority("businessindia", match_pairs)[0])
        self.assertTrue(is_priority("theken", match_pairs)[0])
        self.assertTrue(is_priority("themorningcontext", match_pairs)[0])
        self.assertTrue(is_priority("deccanherald", match_pairs)[0])
        self.assertTrue(is_priority("deccanchronicle", match_pairs)[0])
        self.assertTrue(is_priority("indiatoday", match_pairs)[0])
        self.assertTrue(is_priority("etbrandequity", match_pairs)[0])
        self.assertTrue(is_priority("amarujala", match_pairs)[0])
        self.assertTrue(is_priority("dainikbhaskar", match_pairs)[0])
        self.assertTrue(is_priority("bhaskarhindi", match_pairs)[0])
        self.assertTrue(is_priority("bhaskarlive", match_pairs)[0])
        self.assertTrue(is_priority("dainikjagran", match_pairs)[0])
        self.assertTrue(is_priority("dailyjagran", match_pairs)[0])
        self.assertTrue(is_priority("navbharattimes", match_pairs)[0])
        self.assertTrue(is_priority("dtnext", match_pairs)[0])
        self.assertTrue(is_priority("mumbaimirror", match_pairs)[0])
        self.assertTrue(is_priority("timesofindia", match_pairs)[0])
        self.assertTrue(is_priority("hindustantimes", match_pairs)[0])
        self.assertTrue(is_priority("newindianexpress", match_pairs)[0])
        self.assertTrue(is_priority("thetribune", match_pairs)[0])
        self.assertTrue(is_priority("thestatesman", match_pairs)[0])
        self.assertTrue(is_priority("thetelegraph", match_pairs)[0])
        self.assertTrue(is_priority("telegraphindia", match_pairs)[0])
        self.assertTrue(is_priority("indianexpress", match_pairs)[0])
        self.assertTrue(is_priority("economictimes", match_pairs)[0])

        # Assert correct mapped names are returned
        matched, pub_name = is_priority("economictimes", match_pairs)
        self.assertTrue(matched)
        self.assertEqual(pub_name, "The Economic Times")
        
        matched, pub_name = is_priority("aninews", match_pairs)
        self.assertTrue(matched)
        self.assertEqual(pub_name, "ANI")

        matched, pub_name = is_priority("theken", match_pairs)
        self.assertTrue(matched)
        self.assertEqual(pub_name, "The Ken")

    def test_publication_scoped_deduplication(self):
        from scraper.heavy_filter import exact_dedup, near_dedup
        
        # Mock articles
        articles = [
            {"title": "Google India makes new investments", "agency": "Times of India", "full_body": "TOI body here"},
            {"title": "Google India makes new investments", "agency": "Times of India", "full_body": "TOI second copy body"}, # Duplicate from same agency (exact)
            {"title": "Google India makes new investments", "agency": "The Economic Times", "full_body": "ET copy body"}, # Same title, different agency
            {"title": "Google India makes new investments", "agency": "Reuters", "full_body": "Reuters copy body"}, # Same title, different agency
        ]
        
        # Test exact dedup
        deduped_exact = exact_dedup(articles)
        self.assertEqual(len(deduped_exact), 3) # TOI (1), ET (1), Reuters (1)
        
        # Verify that we preserved the correct agencies
        agencies = [art["agency"] for art in deduped_exact]
        self.assertIn("Times of India", agencies)
        self.assertIn("The Economic Times", agencies)
        self.assertIn("Reuters", agencies)
        
        # Test near dedup within publications
        near_dup_articles = [
            {"title": "YouTube launches new feature", "agency": "TOI", "full_body": "YouTube has launched a new feature for creator safety."},
            {"title": "YouTube launches new feature!", "agency": "TOI", "full_body": "YouTube has launched a new feature for creator safety!"}, # Near duplicate, same agency
            {"title": "YouTube launches new feature", "agency": "ET", "full_body": "YouTube has launched a new feature for creator safety."}, # Near duplicate, different agency
        ]
        
        deduped_near = near_dedup(near_dup_articles, threshold=0.80)
        # Should deduplicate the two TOI articles into 1, but keep the ET article
        self.assertEqual(len(deduped_near), 2)
        
        agencies_near = [art["agency"] for art in deduped_near]
        self.assertIn("TOI", agencies_near)
        self.assertIn("ET", agencies_near)


if __name__ == "__main__":
    unittest.main()

