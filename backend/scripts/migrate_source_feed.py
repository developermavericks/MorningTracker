import asyncio
from sqlalchemy import text
from db.database import engine

async def migrate():
    async with engine.begin() as conn:
        print("Starting migration...")
        try:
            await conn.execute(text("ALTER TABLE articles ADD COLUMN source_feed VARCHAR"))
            await conn.commit() # Forced commit
            print("Successfully added 'source_feed' (COMMITTED).")
        except Exception as e:
            await conn.rollback()
            if "already exists" in str(e):
                print("'source_feed' column already exists.")
            else:
                print(f"Error adding 'source_feed': {e}")
        
        # Ensure 'hashed_password' is in users (it should be, but let's be safe)
        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN hashed_password VARCHAR"))
            print("Successfully added 'hashed_password' to 'users' table.")
        except Exception as e:
            if "already exists" in str(e):
                pass
            else:
                print(f"Error adding 'hashed_password' to 'users': {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
