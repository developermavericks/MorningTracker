# NEXUS Backend Verification Guide 🛰️🛡️

This guide provides three distinct levels of verification to certify that your backend is 100% operational and scraping correctly.

---

## 🟢 Level 1: System Heartbeat (Instant)
The fastest way to check if the core services (Database & Redis) are alive.

**How to check:**
1. Open your browser to: `https://morningtracker-production.up.railway.app/api/health`
2. **Expected Response:**
   ```json
   {
     "status": "healthy",
     "services": {
       "database": "connected",
       "redis": "connected"
     }
   }
   ```
   *If you see "degraded", it means one of the databases is having connection issues.*

---

## 🔵 Level 2: Browser Warm-up (Functional)
This verifies that the **Playwright Browsing Engine** is correctly installed on the Railway server and can launch a headless browser.

**How to check:**
1. Open your browser to: `https://morningtracker-production.up.railway.app/api/health/browser`
2. **Expected Response:**
   ```json
   {
     "status": "ready",
     "latency_ms": 1245
   }
   ```
   *Note: The first time you run this, it may take 5-10 seconds to "warm up" the container.*

---

## 🟡 Level 3: End-to-End Scrape Proof (Functional)
This is the "Smoke Test" to ensure news articles are actually flowing into your database.

**How to check:**
1. Go to your **Brand Tracker** page in the UI.
2. Click **"Add Brand Node"** and add a test brand (e.g., `NVIDIA`).
3. Click the **"Scrape"** icon next to it.
4. Navigate to **"Mission Control"** (Jobs).
5. **Success Indicator:**
   - Status changes from `PENDING` ➔ `RUNNING` ➔ `COMPLETED`.
   - The **"Yield"** (Total Insights Gathered) count on the Dashboard starts increasing.
   - Go to the **"Articles"** page; you should see fresh articles with the `NVIDIA` sector label.

---

## 🛠️ Debugging Tools
If any of the above fails, check the **System Telemetry** (Diagnostics) page in your UI. It provides a detailed breakdown of:
- **Groq API**: Check if your AI key is active.
- **Extraction Grid**: Check if workers are running.
- **Error Logs**: View the direct intelligence stream for any hidden failures.
