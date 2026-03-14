import asyncio
import httpx
import time
import sys
import os
from datetime import date, timedelta

# Ensure we can import from backend
sys.path.append(os.getcwd())

async def run_enterprise_test():
    print("NEXEUS ENTERPRISE LEVEL FUNCTIONAL TEST")
    print("==========================================")
    
    BASE_URL = "http://localhost:8000"
    
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60, follow_redirects=True) as client:
        # 1. API Connectivity check
        print("\n[1/5] Checking API Connectivity...")
        try:
            res = await client.get("/")
            if res.status_code == 200:
                print(f"  [OK] API Root: OK ({res.json().get('status')})")
            else:
                print(f"  [FAIL] API Root: FAILED ({res.status_code})")
        except Exception as e:
            print(f"  [ERROR] API Connection Error: {e}")
            return

        # 2. Auth Test
        print("\n[2/5] Testing Authentication...")
        test_email = f"test_{int(time.time())}@example.com"
        test_pass = "testpass123"
        token = None
        
        try:
            # Register
            await client.post("/api/auth/register", json={
                "email": test_email,
                "password": test_pass,
                "name": "Test User"
            })
            # Login
            login_res = await client.post("/api/auth/login", data={
                "username": test_email,
                "password": test_pass
            })
            if login_res.status_code == 200:
                token = login_res.json().get("access_token")
                print("  [OK] Auth: Login successful, token acquired.")
            else:
                print(f"  [FAIL] Auth: Login failed ({login_res.status_code})")
        except Exception as e:
            print(f"  [ERROR] Auth Error: {e}")

        headers = {"Authorization": f"Bearer {token}"} if token else {}

        # 3. Health check
        print("\n[3/5] Verifying Service Health...")
        res = await client.get("/api/diagnostics/health")
        if res.status_code == 200:
            health_data = res.json()
            if health_data.get("overall") == "healthy":
                print(f"  [OK] Health: GREEN (Status: {health_data.get('overall')})")
            else:
                print(f"  [WARNING] Health: {health_data.get('overall').upper()}")
        else:
            print(f"  [FAIL] Health: FAILED ({res.status_code})")

        # 4. Monitor Discovery Count
        print("\n[4/5] Checking for Active Jobs...")
        res = await client.get("/api/scrape/jobs", headers=headers)
        if res.status_code == 200:
            jobs = res.json()
            if jobs:
                job = jobs[0]
                print(f"  [INFO] Found existing Job ID: {job['id']} ({job['status']})")
            else:
                print("  [INFO] No jobs currently in progress for this test user.")
        else:
            print(f"  [FAIL] Job fetch failed: {res.status_code}")

        # 5. Article Retrieval
        print("\n[5/5] Testing Article Data Integrity...")
        res = await client.get("/api/articles/", headers=headers, params={"page_size": 10})
        if res.status_code == 200:
            data = res.json()
            articles = data.get("articles", [])
            print(f"  [OK] Successfully retrieved {len(articles)} articles (Total: {data.get('total')})")
            for a in articles[:3]:
                has_body = "YES" if a.get("full_body") else "NO"
                print(f"    - [{a.get('id')}] {a['title'][:40]}... | Body:{has_body}")
        else:
            print(f"  [FAIL] Article fetch failed: {res.status_code}")

    print("\n==========================================")
    print(" ENTERPRISE TEST COMPLETE ")
    print("==========================================\n")

if __name__ == "__main__":
    asyncio.run(run_enterprise_test())
