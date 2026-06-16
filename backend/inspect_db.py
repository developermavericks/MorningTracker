import os
import sys
from sqlalchemy import select

# Add backend to PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db.database import get_db_sync, Article

def inspect_articles():
    print("=== Inspecting Database Articles ===")
    with get_db_sync() as db:
        stmt = select(Article).order_by(Article.scraped_at.desc()).limit(10)
        res = db.execute(stmt)
        articles = res.scalars().all()
        
        if not articles:
            print("No articles found in the database!")
            return
            
        for i, a in enumerate(articles, 1):
            print(f"\n[{i}] Title: {a.title}")
            print(f"    Author: {a.author}")
            print(f"    Agency: {a.agency}")
            print(f"    Summary: {a.summary[:60] if a.summary else 'None'}")
            print(f"    Extra Metadata: {a.extra_metadata}")

if __name__ == "__main__":
    inspect_articles()
