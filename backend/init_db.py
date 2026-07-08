#!/usr/bin/env python
"""Initialize database with all tables including Heavy Automation."""
from db.database import init_db_sync

if __name__ == "__main__":
    init_db_sync()
    print("[OK] Database initialized successfully!")
