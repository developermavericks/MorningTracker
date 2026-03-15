# NEXUS Production Deployment Guide

This guide details the steps to deploy the NEXUS News Tracker to a production environment using Railway (Backend/DB/Redis) and Vercel (Frontend).

## Prerequisites
- [Railway.app](https://railway.app) account
- [Vercel](https://vercel.com) account
- [SendGrid](https://sendgrid.com) API Key (for notifications)
- [Groq](https://console.groq.com) API Key
- [Webshare.io](https://www.webshare.io) Rotating Proxy (Backconnect URL)
- Google Cloud Console Project (for OAuth 2.0)

---

## 1. Backend Infrastructure (Railway)

### Step 1.1: Database & Redis
1. Create a new project on Railway.
2. Add a **PostgreSQL** service.
3. Add a **Redis** service.
   - Go to Redis settings -> Config -> Enable **Append Only File (AOF)**.

### Step 1.2: Backend Deployment
1. Link your GitHub repository to Railway.
2. Select the `backend` directory (or root if using the provided `railway.toml`).
3. Configure the following environment variables:
   - `DATABASE_URL`: (Railway will auto-populate this from the PG service)
   - `REDIS_URL`: (Railway will auto-populate this from the Redis service)
   - `JWT_SECRET_KEY`: `openssl rand -hex 32`
   - `GROQ_API_KEY`: Your Groq API key
   - `WEBSHARE_PROXY_URL`: Your Webshare backconnect URL (e.g., `http://user:pass@p.webshare.io:80`)
   - `GOOGLE_CLIENT_ID`: From Google Cloud Console
   - `GOOGLE_CLIENT_SECRET`: From Google Cloud Console
   - `FRONTEND_URL`: Your Vercel deployment URL (e.g., `https://nexus-tracker.vercel.app`)
   - `DB_POOL_SIZE`: `20`
   - `DB_MAX_OVERFLOW`: `10`

### Step 1.3: Celery Workers & Beat (All-in-One Budget Option)
To save on Railway costs, you can run everything in a single process.
1. Create ONE additional "Empty Service" instances on Railway originating from the same repo.
2. Rename it to `Nexus-Worker-Master`.
3. **Custom Start Command:**
   `sh -c "celery -A celery_app worker --loglevel=info --concurrency=4 -Q celery,enrichment -B"`
   *Note: The `-B` flag starts the scheduler (Beat) inside the worker.*
4. **Environment Variables:**
   - Must match the `MorningTracker` service exactly.

---

## 2. Frontend Deployment (Vercel)

### Step 2.1: Import Project
1. Import the repository into Vercel.
2. Set the Root Directory to `frontend`.

### Step 2.2: Environment Variables
1. Add `VITE_API_BASE_URL`: Your Railway Backend URL (e.g., `https://backend-production.up.railway.app`).

### Step 2.3: Build Settings
- Framework: `Vite`
- Build Command: `npm run build`
- Output Directory: `dist`

---

## 3. Post-Deployment Verification
1. Navigate to your Vercel URL.
2. Log in via Google OAuth.
3. Start a small 1-day scrape mission.
4. Verify progress appears in **Mission Control**.
5. Once complete, download the **Export Report (.xlsx)** and verify formatting.

---

## 4. Maintenance & Operations
- **Database Backups:** Railway performs automatic backups.
- **Log Monitoring:** Use Railway's "Live Logs" to monitor Celery workers for proxy or AI rate limits.
- **Scaling:** If scraping speed decreases, increase the number of Railway replicas for the Scraper Worker.
