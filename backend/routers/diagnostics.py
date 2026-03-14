import os
import httpx
from datetime import datetime
from fastapi import APIRouter
from sqlalchemy import select, func, text
from db.database import get_db, ScrapeJob, Article

router = APIRouter()
_diag_cache = {"data": None, "timestamp": None}

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
