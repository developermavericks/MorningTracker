import asyncio
import sys
import uvicorn
import os

if __name__ == "__main__":
    if sys.platform == 'win32':
        print("FORCE: Setting WindowsProactorEventLoopPolicy...")
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

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
