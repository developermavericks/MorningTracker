import sys, os, asyncio
# Ensure project root is in PYTHONPATH
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_root)

# Import the init_db function from backend.db.database
from backend.db import database

async def main():
    await database.init_db()
    print('Database schema initialized')

if __name__ == '__main__':
    asyncio.run(main())
