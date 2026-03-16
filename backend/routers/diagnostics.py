import os
import httpx
from datetime import datetime
from fastapi import APIRouter
from sqlalchemy import select, func, text
from db.database import get_db, ScrapeJob, Article
from .auth_utils import get_auth_user as get_current_user, TokenData
from celery_app import app as celery_app

router = APIRouter()
_diag_cache = {"data": None, "timestamp": None}

@router.get("/grok")
async def test_grok():
    """Quick test of Grok API - verifies key is working and model exists. Does NOT use enrichment credits."""
    XAI_API_KEY = os.getenv("XAI_API_KEY", "")
    if not XAI_API_KEY:
        return {"status": "error", "message": "XAI_API_KEY environment variable is not set"}
    
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.x.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {XAI_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "grok-3",
                    "messages": [{"role": "user", "content": "Reply with only the word: WORKING"}],
                    "max_tokens": 5,
                    "temperature": 0
                }
            )
        if resp.status_code == 200:
            reply = resp.json()["choices"][0]["message"]["content"].strip()
            return {"status": "ok", "model": "grok-3", "response": reply, "message": "Grok API is active and working!"}
        else:
            return {"status": "error", "http_code": resp.status_code, "detail": resp.json()}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/browser")
async def check_browser():
    """Verify Playwright can launch."""
    from scraper.engine import test_browser_launch
    return await test_browser_launch()

@router.get("/celery")
async def check_celery():
    """Check if any Celery workers are active."""
    try:
        i = celery_app.control.inspect()
        active = i.active()
        if active is None:
            return {"status": "error", "message": "No response from workers (broker issue or no workers running)"}
        return {"status": "online", "workers": list(active.keys())}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/health")
async def get_system_health():
    """Industrial-grade diagnostics."""
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    now = datetime.now()
    if _diag_cache["data"] and _diag_cache["timestamp"] and (now - _diag_cache["timestamp"]).total_seconds() < 60:
        return _diag_cache["data"]

    status = {
        "database": {"status": "unknown"}, 
        "groq_api": {"status": "unknown"}, 
        "playwright": {"status": "unknown"}, 
        "jobs": {"status": "unknown"}
    }
    overall = "healthy"
    
    # 1. Database Check
    try:
        async with get_db() as db:
            await db.execute(text("SELECT 1"))
        status["database"] = {"status": "online", "message": "Connected"}
    except Exception as e:
        status["database"] = {"status": "offline", "message": str(e)}
        overall = "degraded"

    # 2. Groq API Check
    if GROQ_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                    json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}
                )
                if res.status_code == 200:
                    status["groq_api"] = {"status": "online", "message": "Authenticated"}
                else:
                    status["groq_api"] = {"status": "error", "message": f"HTTP {res.status_code}"}
        except Exception:
            status["groq_api"] = {"status": "offline"}
    else:
        status["groq_api"] = {"status": "offline", "message": "Key missing"}

    # 3. Playwright Check
    try:
        import shutil
        if shutil.which("playwright"):
            status["playwright"] = {"status": "online"}
        else:
            status["playwright"] = {"status": "warning"}
    except:
        status["playwright"] = {"status": "offline"}

    # 4. Jobs Check
    try:
        async with get_db() as db:
            failed_res = await db.execute(select(func.count(ScrapeJob.id)).where(ScrapeJob.status.in_(['failed', 'interrupted', 'partial'])))
            failed = failed_res.scalar() or 0
            
            running_res = await db.execute(select(func.count(ScrapeJob.id)).where(ScrapeJob.status == 'running'))
            running = running_res.scalar() or 0
            
            status["jobs"] = {
                "status": "online",
                "failed": failed,
                "running": running
            }
    except:
        pass

    res = {"overall": overall, "components": status, "timestamp": now.isoformat()}
    _diag_cache["data"] = res
    _diag_cache["timestamp"] = now
    return res

@router.post("/emergency-stop")
async def emergency_stop():
    """Aggressively halt all background activity and clear queues."""
    results = {"actions": []}
    
    # 1. Purge Queues
    try:
        purged = celery_app.control.purge()
        results["actions"].append(f"Purged {purged} tasks from queues")
    except Exception as e:
        results["actions"].append(f"Purge failed: {e}")

    # 2. Revoke active tasks
    try:
        celery_app.control.revoke("all", terminate=True)
        results["actions"].append("Sent broadcast revoke to all workers")
    except Exception as e:
        results["actions"].append(f"Revoke failed: {e}")

    # 3. DB Cleanup
    try:
        async with get_db() as db:
            from sqlalchemy import update
            stmt = (
                update(ScrapeJob)
                .where(ScrapeJob.status.in_(['running', 'pending']))
                .values(status='interrupted', error='Emergency stop triggered')
            )
            await db.execute(stmt)
            await db.commit()
            results["actions"].append("Marked active jobs as interrupted in DB")
    except Exception as e:
        results["actions"].append(f"DB update failed: {e}")

    # 4. Global Kill Switch in Redis
    try:
        from scraper.llm import get_redis
        r = await get_redis()
        # Set a 5-minute global stop to allow workers to exit cleanly
        await r.set("nexus:global_stop", "1", ex=300)
        results["actions"].append("Triggered 5-minute GLOBAL STOP flag")
    except Exception as e:
        results["actions"].append(f"Global stop flag failed: {e}")

    return {"status": "success", "results": results}
