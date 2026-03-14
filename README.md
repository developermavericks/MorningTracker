# ⬡ NEXUS — Global News Intelligence Scraper

A full-stack web application for scraping, storing, and browsing news articles globally by sector, region, and date range.

---

## 🚀 Quick Start (Single Command)

### Prerequisites

- **Python 3.10+** with `venv`
- **Node.js 18+** with `npm`
- **Playwright Chromium** browser (`playwright install chromium`)

### Run the Application

```powershell
# Windows PowerShell — starts both backend + frontend
.\start.ps1
```

```cmd
# Windows CMD alternative
start.bat
```

This single command will:
1. Kill any existing processes
2. Load environment variables from `backend/.env`
3. Start the FastAPI backend on **http://localhost:8000**
4. Start the Vite frontend on **http://localhost:5173**
5. Open the dashboard in your default browser

Press `Ctrl+C` to stop everything.

---

## 🔧 First-Time Setup

```bash
# 1. Backend setup
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
playwright install chromium

# 2. Environment variables
# Create backend/.env with:
echo GROQ_API_KEY=your_groq_api_key_here > .env

# 3. Frontend setup
cd ../frontend
npm install

# 4. Go back to root and launch
cd ..
.\start.ps1
```

---

## 🏗 Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                         NEXUS                                │
│                                                              │
│  React Frontend (Vite :5173)                                 │
│    ├── Dashboard     — stats, body coverage, quick actions   │
│    ├── New Scrape    — configure & launch jobs               │
│    ├── Articles      — browse, filter, search, export CSV    │
│    └── Jobs          — live monitoring, error visibility     │
│                          │ Vite Proxy (/api → :8000)         │
│  FastAPI Backend (:8000)                                     │
│    ├── /api/scrape   — trigger & monitor scrape jobs         │
│    ├── /api/articles — query, filter, export                 │
│    └── Startup       — auto-recovery of interrupted jobs     │
│                          │                                   │
│  Scraper Engine (Playwright + BeautifulSoup)                 │
│    ├── Google News + Bing News RSS discovery                 │
│    ├── Direct headless Chromium scraping (fast)               │
│    └── Paywall bypass enrichment (deferred, on-demand)       │
│                          │                                   │
│  SQLite Database (auto-migrating schema)                     │
│    ├── articles      — all scraped article data              │
│    ├── scrape_jobs   — job tracking & progress               │
│    └── articles_fts  — full-text search index                │
└──────────────────────────────────────────────────────────────┘
```

---

## ⚡ How Scraping Works

### Phase 1: Main Scrape (Fast)
When you launch a scrape job, NEXUS uses **direct scraping only**:
1. **Discovery** — Queries Google News + Bing News RSS feeds with sector keywords × region cities × date range
2. **Direct Extraction** — Each URL is visited by headless Chromium, HTML is parsed to extract article body
3. **Storage** — Articles are saved immediately with deduplication by URL
4. **Progress** — Dashboard updates every 25 articles processed

### Phase 2: Enrichment (On-Demand)
Articles with missing/junk body text can be enriched later via the Dashboard's **"Enrich Missing Bodies"** button:

```
For every article with junk/paywall body:
                    │
           Direct Scrape
           (< 150 words or junk)
                    │
            ┌───────▼───────┐
            │   12ft.io     │  ← Strips paywall JS
            └───────┬───────┘
                    │ (if < 300 words)
            ┌───────▼───────┐
            │  archive.ph   │  ← Cached snapshot
            └───────┬───────┘
                    │ (if < 300 words)
            ┌───────▼───────┐
            │ Google Cache  │  ← Pre-paywall version
            └───────┬───────┘
                    │ (if < 300 words)
            ┌───────▼───────┐
            │removepaywall  │  ← removepaywall.com
            └───────┬───────┘
                    │ (if < 300 words)
            ┌───────▼───────┐
            │  Bing Cache   │  ← Bing's cached copy
            └───────┘
                    │
           Returns whichever
           service had MOST words
```

This two-phase approach means **scraping is fast** (seconds per article) and **enrichment is thorough** (tries 5 bypass services per paywalled article).

---

## 📊 Database Schema

### `articles` table

| Column         | Type        | Description                          |
|----------------|-------------|--------------------------------------|
| id             | SERIAL      | Primary key                          |
| title          | TEXT        | Article headline                     |
| url            | TEXT UNIQUE | Source URL (deduplicated)            |
| full_body      | TEXT        | Full article text content            |
| author         | TEXT        | Author name                          |
| agency         | TEXT        | Publishing organization              |
| published_at   | TIMESTAMPTZ | Original publication timestamp       |
| sector         | TEXT        | Sector (ai, finance, health, etc.)   |
| region         | TEXT        | Geographic region                    |
| word_count     | INTEGER     | Word count of body text              |
| summary        | TEXT        | AI-generated 3-bullet summary       |
| title_hash     | TEXT        | MD5 of normalized title (dedup)      |
| scraped_at     | TIMESTAMPTZ | When we captured it                  |
| scrape_job_id  | TEXT        | Links back to the originating job    |

### `scrape_jobs` table

| Column         | Type        | Description                          |
|----------------|-------------|--------------------------------------|
| id             | TEXT        | UUID primary key                     |
| sector         | TEXT        | Target sector                        |
| region         | TEXT        | Target region                        |
| date_from      | DATE        | Start of date range                  |
| date_to        | DATE        | End of date range                    |
| status         | TEXT        | pending/running/completed/failed/interrupted/partial |
| total_found    | INTEGER     | URLs discovered via RSS              |
| total_scraped  | INTEGER     | Articles successfully processed      |
| error          | TEXT        | Error message (if failed)            |
| started_at     | TIMESTAMPTZ | Job start time                       |
| completed_at   | TIMESTAMPTZ | Job end time                         |

---

## 🔌 API Reference

| Method | Endpoint                      | Description                         |
|--------|-------------------------------|-------------------------------------|
| POST   | `/api/scrape/start`           | Launch a new scrape job             |
| POST   | `/api/scrape/enrich`          | Start body enrichment (paywall bypass) |
| GET    | `/api/scrape/jobs`            | List all jobs                       |
| GET    | `/api/scrape/job/{id}`        | Get job status + progress           |
| DELETE | `/api/scrape/job/{id}`        | Delete job and its articles         |
| GET    | `/api/scrape/options`         | List available sectors/regions      |
| GET    | `/api/articles/`              | Query articles (with filters)       |
| GET    | `/api/articles/{id}`          | Get full article by ID              |
| GET    | `/api/articles/export/csv`    | Export filtered articles as CSV     |
| GET    | `/api/articles/stats/summary` | Dashboard stats + body coverage     |

### Start Scrape Job (POST `/api/scrape/start`)

```json
{
  "sector": "artificial intelligence",
  "region": "india",
  "date_from": "2024-01-01",
  "date_to": "2024-01-15"
}
```

> **Note:** Maximum date range is 30 days per job.

---

## 🌍 Supported Sectors

`artificial intelligence`, `technology`, `finance`, `business`, `politics`,
`health`, `environment`, `sports`, `lifestyle`, `education`

## 🗺 Supported Regions

`global`, `india`, `usa`, `uk`, `canada`, `japan`, `australia`

---

## 🛡 Production Hardening

NEXUS includes several reliability features:

- **Pre-flight browser check** — Verifies Playwright can launch before accepting jobs
- **Date range guard** — Max 30 days per job to prevent resource exhaustion
- **Concurrency guard** — Max 2 concurrent scrape jobs
- **Auto-recovery** — Jobs in `running`/`pending` state are auto-marked `interrupted` on restart
- **Batch progress** — Progress updates every 25 articles (visible in real-time on dashboard)
- **Schema auto-migration** — New columns are auto-added on startup (no manual SQL needed)
- **Title deduplication** — Cross-URL duplicate detection via MD5 of normalized title
- **CAPTCHA detection** — Junk body filter catches CAPTCHA pages from bypass services

---

## 📁 Project Structure

```
Crexito_Scrape/
├── start.ps1                # ← SINGLE COMMAND TO START EVERYTHING
├── start.bat                # ← CMD alternative
├── backend/
│   ├── main.py              # FastAPI app entry + startup hooks
│   ├── requirements.txt
│   ├── .env                 # GROQ_API_KEY (create manually)
│   ├── db/
│   │   └── database.py      # SQLite/PostgreSQL + auto-migration
│   ├── routers/
│   │   ├── scrape.py        # Job management + validation guards
│   │   └── articles.py      # Article query + export + stats
│   └── scraper/
│       ├── engine.py        # Core scraping (fast, direct-only)
│       └── enrichment.py    # Paywall bypass waterfall (on-demand)
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Shell + live API health indicator
│   │   ├── api.js           # API client (uses Vite proxy)
│   │   ├── index.css        # Full design system
│   │   └── pages/
│   │       ├── Dashboard.jsx       # Stats + body coverage + quick actions
│   │       ├── NewScrape.jsx       # Job form + date validation
│   │       ├── ArticlesBrowser.jsx # Table + filters + export
│   │       └── Jobs.jsx            # Live monitoring + error column
│   ├── index.html
│   ├── vite.config.js       # Proxy /api → :8000
│   └── package.json
└── README.md
```

---

## ⚠️ Important Notes

### On Web Scraping
- Discovery uses Google News + Bing News RSS feeds (no API keys needed)
- **Direct scraping** is fast (~1-3 seconds per article)
- **Paywall bypass** is deferred to enrichment (slower but thorough)
- All articles are deduplicated by URL and normalized title hash
- Respectful crawling with concurrency limits built in

### On Data Quality
- Body coverage is tracked on the dashboard (target: >80%)
- Articles with junk bodies can be enriched on-demand via the dashboard
- AI summaries require a valid `GROQ_API_KEY` in `backend/.env`
- Author/agency extraction is heuristic-based and may not work on all sites
