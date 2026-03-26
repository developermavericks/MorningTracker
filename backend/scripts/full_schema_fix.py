import asyncio
from sqlalchemy import text
from db.database import engine

async def full_fix():
    async with engine.begin() as conn:
        print("Checking current columns...")
        result = await conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'articles'
        """))
        cols = [row[0] for row in result]
        print("Existing columns:", cols)
        
        if 'source_feed' not in cols:
            print("Adding 'source_feed'...")
            # Use raw SQL connection for ALTER TABLE if possible, or just force execute
            await conn.execute(text("ALTER TABLE articles ADD COLUMN source_feed VARCHAR"))
            print("ADD COLUMN executed.")
        else:
            print("'source_feed' already exists in schema.")

    # Second pass to verify
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'articles'"))
        cols = [row[0] for row in result]
        print("Columns after migration:", cols)
        
        if 'source_feed' in cols:
            print("SUCCESS: column found.")
        else:
            print("FAILURE: column still missing.")

if __name__ == "__main__":
    asyncio.run(full_fix())
