import asyncio
import sys
import uvicorn
import os
import warnings

# Suppress warnings for cleaner startup
warnings.filterwarnings("ignore", category=DeprecationWarning)

if __name__ == "__main__":
    if sys.platform == 'win32':
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass

    # Import app after policy is set
    from main import app
    
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    print(f"Starting NEXUS Backend on {host}:{port} with loop=asyncio (reload=OFF)")
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=False,
        loop="asyncio"
    )
