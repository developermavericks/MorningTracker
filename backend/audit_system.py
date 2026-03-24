import asyncio
import os
import sys
import uuid
import httpx
from datetime import date, datetime
from sqlalchemy import select, text

# Add backend to path
sys.path.append(os.getcwd())

from db.database import init_db, get_db, User, ScrapeJob
from celery_app import app as celery_app

async def test_api_endpoints():
    print("\n[Audit] Testing Core API Endpoints...")
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        try:
            # 1. Root
            res = await client.get("/")
            print(f"  - GET /: {res.status_code}")
            
            # 2. Health
            res = await client.get("/api/diagnostics/health")
            print(f"  - GET /health: {res.status_code} ({res.json().get('overall')})")
            
            # 3. Options
            res = await client.get("/api/scrape/options")
            print(f"  - GET /options: {res.status_code} ({len(res.json().get('sectors', []))} sectors)")
        except Exception as e:
            print(f"  - ⚠️ API Server not reachable: {e}")

async def audit_system():
    print("🛡️ NEXEUS GLOBAL SYSTEM AUDIT & HARDENING")
    print("==========================================")

    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    # 1. Database & ORM Audit
    print("\n[1/4] Auditing Database & SQLAlchemy Models...")
    try:
        await init_db()
        async with get_db() as db:
            # Verify basic queries
            await db.execute(text("SELECT 1"))
            print("  ✅ Core Connection: STABLE")
            
            user_count = (await db.execute(select(text("count(*)")).select_from(User))).scalar()
            print(f"  ✅ User Model: OK (Count: {user_count})")
            
            job_count = (await db.execute(select(text("count(*)")).select_from(ScrapeJob))).scalar()
            print(f"  ✅ ScrapeJob Model: OK (Count: {job_count})")
    except Exception as e:
        print(f"  ❌ DB Audit Failed: {e}")

    # 2. Distributed Component Audit
    print("\n[2/4] Auditing Celery & Broker...")
    try:
        import redis
        r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        r.ping()
        print("  ✅ Redis Broker: ONLINE")
        
        # Check Celery workers (ping)
        i = celery_app.control.inspect()
        ping_res = i.ping()
        if ping_res:
            print(f"  ✅ Celery Workers: ACTIVE ({len(ping_res)} nodes)")
        else:
            print("  ⚠️ Celery Workers: OFFLINE (Tasks will be queued but not processed)")
    except Exception as e:
        print(f"  ❌ Distributed Audit Failed: {e}")

    # 3. AI Engine Audit
    print("\n[3/4] Auditing AI Enrichment Engines...")
    # Grok (xAI) Check
    from scraper.llm import XAI_API_KEYS, GROQ_API_KEYS, OLLAMA_BASE_URL
    is_placeholder = any("your_xai_api_key" in k.lower() for k in XAI_API_KEYS)
    if not XAI_API_KEYS or is_placeholder:
        print("  ⚠️ Grok (xAI): UNCONFIGURED")
        # Fallback check for Groq
        from scraper.llm import GROQ_API_KEYS
        is_groq_placeholder = any("your_groq_api_key" in k.lower() for k in GROQ_API_KEYS)
        if GROQ_API_KEYS and not is_groq_placeholder:
            print(f"  ℹ️  Legacy Groq Found: CONFIGURED ({len(GROQ_API_KEYS)} keys)")
        else:
            print("  ⚠️ Summarization Engine: TOTALLY DISABLED (No xAI or Groq keys)")
    else:
        print(f"  ✅ Grok (xAI): CONFIGURED ({len(XAI_API_KEYS)} keys)")

    # Ollama Check
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            res = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if res.status_code == 200:
                print(f"  ✅ Ollama Engine: ONLINE ({OLLAMA_BASE_URL})")
            else:
                print(f"  ⚠️ Ollama Engine: DEGRADED ({res.status_code})")
    except Exception:
        print(f"  ⚠️ Ollama Engine: OFFLINE (Extraction disabled)")

    # 4. API & Integration Audit
    await test_api_endpoints()

    print("\n==========================================")
    print(" ✨ SYSTEM HARDENING AUDIT COMPLETE ✨")
    print("==========================================\n")

if __name__ == "__main__":
    asyncio.run(audit_system())
