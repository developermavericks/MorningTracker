import asyncio
from sqlalchemy import text
from db.database import engine

async def test_query():
    async with engine.connect() as conn:
        print("Testing direct query on articles table...")
        try:
            # Try to select the problematic column
            result = await conn.execute(text("SELECT source_feed FROM articles LIMIT 1"))
            print("Successfully selected 'source_feed'.")
            
            # Try the full count query that failed
            result = await conn.execute(text("""
                SELECT count(*) 
                FROM (SELECT * FROM articles) AS anon_1
            """))
            print("Successfully executed count query. Total:", result.scalar())
        except Exception as e:
            print("QUERY FAILED:", e)

if __name__ == "__main__":
    asyncio.run(test_query())
