import sys
import os
import unittest
from unittest.mock import MagicMock, patch
from datetime import date

# Add backend to sys.path
sys.path.append(os.path.join(os.getcwd(), "backend"))

# Mocking parts of engine to isolate discover_articles
with patch('scraper.engine.get_db_sync'), \
     patch('scraper.engine.load_proxies', return_value=[]), \
     patch('scraper.network.NetworkHandler.get_google_rss', return_value="<rss></rss>"), \
     patch('scraper.engine.is_job_cancelled', return_value=False), \
     patch('scraper.engine.Pool'):
    
    from scraper.engine import discover_articles

class TestDiscoveryContext(unittest.TestCase):
    def test_brand_track_no_modifiers(self):
        """
        Verify that if is_brand_track is True, no modifiers are added to window_queries.
        """
        keywords = ["Scapia"]
        # We need to peek into the function or mock the network call to see what queries it gets
        with patch('scraper.engine.Pool') as MockPool:
            pool_instance = MockPool.return_value
            
            # Call discover_articles
            discover_articles(keywords, date.today(), "IN", "india", "test-job", is_brand_track=True)
            
            # Check the queries spawned
            spawn_calls = pool_instance.spawn.call_args_list
            spawned_queries = [call[0][1] for call in spawn_calls]
            
            # If is_brand_track=True, spawned_queries should ONLY be the exact keywords
            # (Note: Google News RSS might add " when:1d" or similar, but the base query should match keywords)
            for q in spawned_queries:
                self.assertEqual(q, "Scapia")

    def test_sector_track_has_modifiers(self):
        """
        Verify that if is_brand_track is False, modifiers ARE added.
        """
        keywords = ["AI"]
        with patch('scraper.engine.Pool') as MockPool:
            pool_instance = MockPool.return_value
            discover_articles(keywords, date.today(), "IN", "india", "test-job", is_brand_track=False)
            
            spawn_calls = pool_instance.spawn.call_args_list
            spawned_queries = [call[0][1] for call in spawn_calls]
            
            # Should have more queries than just the keyword
            self.assertTrue(len(spawned_queries) > len(keywords))
            
            # At least one query should contain a modifier
            has_modifier = any(" " in q for q in spawned_queries)
            self.assertTrue(has_modifier)

if __name__ == "__main__":
    unittest.main()
