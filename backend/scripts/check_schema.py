import os
import asyncio
from sqlalchemy import text
from db.database import engine

async def check_schema():
    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'articles'
        """))
        columns = [row[0] for row in result]
        with open("schema_status.txt", "w") as f:
            f.write("Columns in 'articles' table:\n")
            for col in columns:
                f.write(f"  - {col}\n")
        
        # Check users table too
        result = await conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'users'
        """))
        users_cols = [row[0] for row in result]
        with open("schema_status.txt", "a") as f:
            f.write("\nColumns in 'users' table:\n")
            for col in users_cols:
                f.write(f"  - {col}\n")

if __name__ == "__main__":
    asyncio.run(check_schema())
