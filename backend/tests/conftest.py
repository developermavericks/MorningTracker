import os
import pytest
import asyncio

# Use a test database - MUST BE SET BEFORE IMPORTING DB.DATABASE
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///test_nexus.db"

from db.database import init_db, engine, engine_sync

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    if os.path.exists("test_nexus.db"):
        os.remove("test_nexus.db")
    print("\nInitializing fresh test database...")
    asyncio.run(init_db())
    yield
    # Properly close connections to avoid File Locked error on Windows
    asyncio.run(engine.dispose())
    engine_sync.dispose()
    if os.path.exists("test_nexus.db"):
        try:
            os.remove("test_nexus.db")
            print("Cleanup: test_nexus.db removed.")
        except Exception as e:
            print(f"Cleanup warning: could not remove test_nexus.db: {e}")

