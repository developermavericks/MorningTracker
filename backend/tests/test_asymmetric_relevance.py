import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
from db.database import get_db_sync, IrrelevantArticle, ZeroResultQuery
from scraper.llm import check_relevance_with_groq
from scraper.engine import discover_articles
from sqlalchemy import select, delete

def test_check_relevance_with_groq_primary_relevant():
    with patch("scraper.llm.check_relevance_with_groq_oss") as mock_oss:
        mock_oss.return_value = ("relevant", "matches context", 0.9)
        
        is_relevant, verdict, reason, score = check_relevance_with_groq(
            "Scapia Credit Card Review", "Scapia is a great travel card", ["Scapia"], "Scapia"
        )
        
        assert is_relevant is True
        assert verdict == "relevant"
        assert score == 0.9
        assert "matches context" in reason
        mock_oss.assert_called_once()

def test_check_relevance_with_groq_primary_uncertain_escalates_and_keeps():
    with patch("scraper.llm.check_relevance_with_groq_oss") as mock_oss:
        mock_oss.side_effect = [
            ("uncertain", "borderline brand mention", 0.5),
            ("relevant", "120b confirmed connection", 0.8)
        ]
        
        is_relevant, verdict, reason, score = check_relevance_with_groq(
            "Travel Trends in 2026", "Travel is picking up in India", ["travel"], "Scapia"
        )
        
        assert is_relevant is True
        assert verdict == "relevant"
        assert score == 0.8
        assert "120b confirmed relevant" in reason
        assert mock_oss.call_count == 2

def test_check_relevance_with_groq_primary_uncertain_escalates_and_rejects():
    with patch("scraper.llm.check_relevance_with_groq_oss") as mock_oss:
        mock_oss.side_effect = [
            ("uncertain", "borderline case", 0.5),
            ("not_relevant", "no travel or fintech context", 0.15)
        ]
        
        is_relevant, verdict, reason, score = check_relevance_with_groq(
            "Unrelated News", "Some random news post", ["travel"], "Scapia"
        )
        
        assert is_relevant is False
        assert verdict == "not_relevant"
        assert score == 0.15
        assert "120b verdict: not_relevant" in reason
        assert mock_oss.call_count == 2

def test_zero_result_query_logging():
    with patch("scraper.engine.NetworkHandler.get_google_rss") as mock_rss:
        mock_rss.return_value = "<rss></rss>"
        
        with get_db_sync() as db:
            db.execute(delete(ZeroResultQuery).where(ZeroResultQuery.query_string == 'emptytestquery'))
            db.commit()
            
        discover_articles(
            keywords=["emptytestquery"],
            day=None,
            geo="IN",
            region_name="india",
            job_id="test_zero_job",
            sector="TestSector"
        )
        
        with get_db_sync() as db:
            log_entry = db.execute(
                select(ZeroResultQuery)
                .where(ZeroResultQuery.query_string == 'emptytestquery')
            ).scalar_one_or_none()
            
            assert log_entry is not None
            assert log_entry.sector == "TestSector"
            assert log_entry.count >= 1

