import os
import sys
import pytest
import asyncio
from datetime import date, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import init_db, get_db, HistoricalJob, HistoricalSubJob, HistoricalArticle
from scraper.historical_engine import create_excel_report, identify_matched_keywords

@pytest.mark.asyncio
async def test_historical_db_initialization():
    await init_db()
    async with get_db() as db:
        from sqlalchemy import select
        res = await db.execute(select(HistoricalJob).limit(1))
        # Ensure model is queryable without error
        assert res is not None

def test_identify_matched_keywords():
    title = "Emeritus partnering with Eruditus and Ashwin Damera for online degrees"
    keywords = ["Emeritus", "Eruditus", "Ashwin Damera", "Random Other"]
    matched = identify_matched_keywords(title, keywords)
    assert "Emeritus" in matched
    assert "Eruditus" in matched
    assert "Ashwin Damera" in matched
    assert "Random Other" not in matched

def test_excel_generation_tmp(tmp_path):
    excel_path = os.path.join(tmp_path, "test_report.xlsx")
    articles = [
        {
            "title": "Test Article Title 1",
            "publication": "Economic Times",
            "url": "https://economictimes.indiatimes.com/test1",
            "published_date": "2024-10-05",
            "matched_keywords": "Emeritus, Eruditus"
        }
    ]
    path = create_excel_report(excel_path, "Test Client", articles)
    assert os.path.exists(path)
    assert os.path.getsize(path) > 1000
