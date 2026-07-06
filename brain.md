# ⬡ NEXUS System Memory & Architecture Map (brain.md)

This document serves as the single source of truth for the **NEXUS Global News Intelligence Scraper and Heavy Automation Pipeline**. It explains the project's layout, database structures, core workflows, and runtime procedures to eliminate the need for full-codebase analysis on every run.

---

## 🎯 System Overview & Capabilities

NEXUS is a production-grade, full-stack intelligence system built to ingest, filter, cluster, enrich, and summarize global news articles by sector, region, and date range. It features two distinct operations:

1. **Standard Scraper**: Discovers articles via Google & Bing News RSS feeds and crawls them in real-time using Playwright + BeautifulSoup. Supports a lazy, multi-service paywall bypass waterfall system (Enrichment).
2. **Heavy Automation Pipeline**: Orchestrates periodic daily/weekly executive briefs for corporate clients (e.g., Google India). It extracts articles, deduplicates using exact matching and TF-IDF cosine similarity, filters utilizing Flashtext (Aho-Corasick) with 500+ keywords and 16 boolean rules, runs LLM gatekeeping, generates executive summaries, creates professional Word reports (`.docx`), and triggers timezone-aware emails.

---

## 📂 Codebase Directory Structure

```
zMorning_Tracker_Synced_Git/
├── start.ps1                # PowerShell launcher script
├── start.bat                # CMD launcher script
├── start.py                 # Multi-process orchestrator (API + Vite + Worker + Beat)
├── README.md                # System quickstart & overview
├── DEPLOYMENT_GUIDE.md      # General deployment details
├── HEAVY_AUTOMATION_SUMMARY.md # Summary of the Heavy Automation implementation
├── backend/
│   ├── main.py              # FastAPI app setup, CORS, endpoints, startup hooks
│   ├── run_backend.py       # Dev script to launch uvicorn
│   ├── celery_app.py        # Celery task router, queues, scheduling configurations
│   ├── requirements.txt     # Python dependencies
│   ├── .env                 # Environment configurations (GROQ_API_KEY, SMTP, DB, Redis)
│   ├── db/
│   │   └── database.py      # SQLAlchemy DB engines (async + sync), tables, auto-migrations
│   ├── routers/
│   │   ├── admin.py         # Admin controls, database resets
│   │   ├── articles.py      # Article searches, filters, exports (CSV), stats
│   │   ├── auth.py          # User registration, logins, JWT auth
│   │   ├── auth_utils.py    # Authentication helpers
│   │   ├── brands.py        # Watched brand keywords
│   │   ├── clients.py       # Client management CRUD
│   │   ├── diagnostics.py   # System checks, server statuses
│   │   ├── feed.py          # RSS feed configuration
│   │   ├── heavy_automation.py # Heavy Automation CRUD, manual runs, previews
│   │   └── scrape.py        # Standard scraper controls (start, stop, enrich)
│   └── scraper/
│       ├── engine.py        # Core scrapers, RSS parser, direct extraction, user-agents
│       ├── browser.py       # Headless Playwright launcher & configuration
│       ├── enrichment.py    # Multi-service paywall bypass engine (12ft, archive.ph, etc.)
│       ├── google_news.py   # Decodes Google News tracker URLs to actual source URLs
│       ├── heavy_filter.py  # Keyword (Aho-Corasick) & 16-Boolean logic evaluators
│       ├── heavy_llm.py     # Groq LLM pipelines (decision model, exec summaries)
│       ├── report_generator.py # Formats corporate data to Word (docx) format
│       ├── search_utils.py  # Boolean logic evaluators for basic keyword checks
│       ├── similarity.py    # TF-IDF vectorization & Cosine Similarity clustering
│       └── tasks.py         # Celery tasks (scrapes, client runs, scheduled watchdogs)
├── frontend/
│   ├── package.json         # Node.js dependencies
│   ├── vite.config.js       # Vite client configuration (proxies /api -> localhost:8000)
│   ├── src/
│   │   ├── App.jsx          # Main application router and core layout shell
│   │   ├── index.css        # Premium global stylesheet & CSS custom properties
│   │   ├── services/
│   │   │   └── api.js       # Axios base client mapping to /api
│   │   └── pages/
│   │       ├── Dashboard.jsx # High-level stats, quick actions, body coverage
│   │       ├── ArticlesBrowser.jsx # News browser table with exports & summaries
│   │       ├── NewScrape.jsx # Standard scrape execution wizard
│   │       ├── Jobs.jsx     # Live monitoring panel for Celery tasks
│   │       └── HeavyAutomation.jsx # Settings interface for Heavy Automation briefs
└── tests/                   # Integration and pipeline tests
```

---

## 🏗️ System Architecture & Orchestration

The application uses a distributed, microservices-friendly layout designed for local development or deployment on host environments (e.g. Railway, Vercel).

```
┌────────────────────────────────────────────────────────────────────────┐
│                        NEXUS ORCHESTRATOR                              │
├────────────────────────────────────────────────────────────────────────┤
│  React Frontend (:5173)                                                │
│       │ Proxies /api queries to backend                                │
│       ▼                                                                │
│  FastAPI Backend Server (:8000)                                        │
│       │ Handles routing, triggers Celery tasks, reads DB               │
│       ▼                                                                │
│  SQLite / PostgreSQL DB                                                │
│       │ Shares schema across API servers & Celery worker nodes         │
│       ▲                                                                │
│       │ Reads/Writes                                                   │
│  Celery Worker (solo / concurrent processes)                           │
│       ▲                                                                │
│       │ Triggers periodically (every 5 mins)                           │
│  Celery Beat Scheduler                                                 │
└────────────────────────────────────────────────────────────────────────┘
```

### Celery Task Routing Configuration

Configured inside [celery_app.py](file:///e:/MAVERICKS/zMorning_Tracker_Synced_Git/backend/celery_app.py). Supported queues:
*   `celery` (Fast I/O): Standard scraping (`run_scrape_task`), article nodes processing, schedule check-ins.
*   `reports` (Long-running CPU tasks): Brief reports generation (`run_client_report_task`) and `run_heavy_automation_task`.

*Note: On Windows, Celery workers run in `solo` mode (`-P solo`) due to compatibility limitations with Celery fork models on Windows OS.*

---

## 🔄 Core Data Flows & Pipelines

### 1. Standard News Ingestion (Two-Phase Scraping)
*   **Phase 1: Discovery & Direct Crawl**
    *   **RSS Query**: Queries Google News & Bing News RSS directories using keywords × region × date ranges.
    *   **Google News URL Resolution**: Decodes redirect URLs via a headless ping method inside [google_news.py](file:///e:/MAVERICKS/zMorning_Tracker_Synced_Git/backend/scraper/google_news.py).
    *   **Playwright Direct Scrape**: Launches a headless Playwright instance with Stealth headers to pull HTML. Checks if body text is junk (< 150 words or loads paywall-blocking JS).
    *   **Database Write**: Inserts successfully parsed content to the `articles` database using URL deduplication.
*   **Phase 2: On-Demand Paywall Enrichment Waterfall**
    *   If articles contain missing/junk body content, a sequential bypass waterfall inside [enrichment.py](file:///e:/MAVERICKS/zMorning_Tracker_Synced_Git/backend/scraper/enrichment.py) queries cached services:
        `12ft.io` ➔ `archive.ph` ➔ `Google Cache` ➔ `removepaywall.com` ➔ `Bing Cache`.
    *   Whichever service recovers the longest word count is saved, followed by LLM-powered body cleaning.

### 2. Heavy Automation Brief Pipeline
The heavy pipeline runs periodically via Celery Beat or manual trigger to generate briefings:

```
[450+ Fetched Articles] 
   │
   ▼ (Exact Dup Check) ─── Normalizes and matches SHA-256 Title hashes.
[320+ Unique Articles]
   │
   ▼ (Near Dup Check) ──── Groups articles using Cosine Similarity on TF-IDF Vectors (Threshold 0.80).
[280+ Cluster Survivors]
   │
   ▼ (Keyword Filter) ──── Aho-Corasick dictionary matches 592 concepts, matching Boolean rules.
[Bucketing Division] ─── 分 Split into:
   ├── Clear Discard (0 relevance keywords matched)
   ├── Clear Keep (High-weight relevance match)
   └── Ambiguous Middle (Low-signal relevance matches)
         │
         ▼ (LLM Judge) ─── Groq API (Haiku) decides whether to retain or discard.
[150+ Final Kept Articles]
   │
   ▼ (LLM Summary) ─────── Summarizes top 50 kept articles; synthesizes Executive Briefing.
[Report Builder] ──────── Writes Master & Filtered `.docx` files using templates on disk.
   │
   ▼ (Timezone Mailer) ─── Sends files to brief/master-doc mailing lists via SMTP.
```

---

## 📊 Database Models & Tables

Defined in [database.py](file:///e:/MAVERICKS/zMorning_Tracker_Synced_Git/backend/db/database.py). Automatically migrates on startup.

### Core Tables

#### `users`
*   **Purpose**: Manages authenticated console logins.
*   **Key Fields**: `id`, `email`, `hashed_password`, `is_active`, `is_admin`.

#### `articles`
*   **Purpose**: Central data storage for all successfully scraped web articles.
*   **Key Fields**: `id`, `title`, `url`, `resolved_url`, `full_body`, `author`, `agency`, `published_at`, `sector`, `region`, `word_count`, `summary`, `title_hash` (MD5 of title), `extra_metadata` (JSON block).

#### `scrape_jobs`
*   **Purpose**: Monitors active, completed, or failed Standard Scrapers.
*   **Key Fields**: `id` (UUID), `sector`, `region`, `status` (`pending`|`running`|`completed`|`failed`|`interrupted`), `total_found`, `total_scraped`, `started_at`, `completed_at`, `current_phase`, `phase_stats` (JSON progress).

### Heavy Automation Configuration & Audit Tables

#### `heavy_companies`
*   **Purpose**: Configuration rules for corporate briefing targets.
*   **Key Fields**: `id`, `name` (e.g. Google India), `sector_match`, `enabled`, `timezone`, `fetch_time` (e.g., "07:00"), `window_hours` (e.g. 24h), `relevancy_method`, `relevance_threshold` (0.0 - 1.0), `llm_judge_enabled`, `mail_send_mode`, `mail_send_time`, `frequency` (Daily/Weekly), `days` (JSON list).

#### `heavy_recipients`
*   **Purpose**: Subscriber email settings per client configuration.
*   **Key Fields**: `id`, `company_id` (FK to `heavy_companies`), `email`, `role` (`brief` (receives filtered doc) or `master_doc` (receives complete run)).

#### `heavy_runs`
*   **Purpose**: Run-history database storing report assets.
*   **Key Fields**: `id`, `company_id`, `status` (`completed`/`failed`), `fetched_count`, `deduped_count`, `relevant_count`, `master_doc_path`, `filtered_doc_path`, `email_status` (`sent`|`pending`|`failed`), `progress_message` (Detailed execution log), `started_at`, `finished_at`.

#### `heavy_run_articles`
*   **Purpose**: Fully auditable pipeline log detailing filter outputs per article.
*   **Key Fields**: `id`, `run_id` (FK to `heavy_runs`), `title`, `url`, `relevance_score`, `included_in_brief` (Boolean), `pillar`, `sub_category`, `matched_keywords` (JSON list), `llm_summary`, `bucket` (`clear_keep`|`ambiguous_middle`|`clear_discard`).

#### `irrelevant_articles`
*   **Purpose**: Local filter index used to cache and skip previously discarded URLs.
*   **Key Fields**: `url` (PK), `title`, `description`, `relevance_score`, `rejection_reason`, `first_seen_at`.

---

## 🔧 Deployment & Local Setup Commands

### 1. Environment Configurations
Create a `backend/.env` file with the following variables:
```bash
# LLM APIs (Groq primary and fallback models)
GROQ_API_KEY=gsk_your_api_key
GROQ_PRIMARY_MODEL=openai/gpt-oss-120b
GROQ_RELEVANCE_MODEL=openai/gpt-oss-20b

# Database connection URL (defaults to news_scraper.db SQLite if empty)
DATABASE_URL=sqlite+aiosqlite:///news_scraper.db

# Message broker for Celery (falls back to sqla+sqlite news_scraper.db if Redis is offline)
REDIS_URL=redis://localhost:6379/0

# SMTP mail parameters (Briefings)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=Nexus Intel Brief <your-email@gmail.com>
ADMIN_EMAIL=admin-alerts@example.com
```

### 2. Multi-Process Startup Command
NEXUS comes with a bootstrapper that configures and launches backend, frontend, celery worker, and beat scheduler concurrently.

```powershell
# Windows PowerShell (Root folder)
.\start.ps1

# Windows CMD (Root folder)
start.bat
```

### 3. Running Services Independently
If debugging a specific process, you can launch components manually:
```bash
# 1. Activate Virtual Environment (Windows)
cd backend
venv\Scripts\activate

# 2. Run API Server (FastAPI)
python run_backend.py

# 3. Run Celery Worker (solo on Windows, concurrency on Linux)
celery -A celery_app worker --loglevel=info -Q orchestrator,scraper_nodes,celery,reports -P solo

# 4. Run Celery Beat Scheduler
celery -A celery_app beat --loglevel=info

# 5. Run Vite Frontend Client (Port 5173)
cd ../frontend
npm run dev
```

---

## 🔍 Diagnostics, Tests & Logs

### Log File Index
*   `backend/api.log`: Web request logs, database connection handles, and general route transactions.
*   `backend/worker.log`: Celery execution reports, scraping pipeline output, LLM request statuses.
*   `backend/beat.log`: Cron jobs dispatcher ticks.
*   `frontend.log`: Vite dev environment compilation messages.

### Running Test Suites
Tests are run using `pytest` inside the backend directory:
```bash
# From backend directory with venv activated:
pytest -v
```
*   `test_heavy_automation_e2e.py`: Tests the entire pipeline end-to-end, simulating discovery, TF-IDF clustering, keyword filters, and docx exports.
*   `test_heavy_demo.py`: Tests the LLM judgment, summarizing, and email delivery system using mock data.

---

## 💡 Troubleshooting & Known Pitfalls

1. **Celery Redis Connection Failures**: If Redis is offline, Celery logs a warning and automatically falls back to an SQLite backend (`news_scraper.db`). When this happens, SQLite is used as the task broker. Task scheduling will still operate, but workers may process requests sequentially.
2. **Playwright Browser Launch Failures**: If Playwright runs into driver compatibility issues on Windows, execute `playwright install chromium` inside the active Python virtual environment.
3. **Database Concurrency and Locks**: SQLite database writes may occasionally trigger `database is locked` issues if standard scraper jobs run concurrently with heavy reports. The database engine resolves this by applying selective pooling configurations (NullPool on workers) and connection timeout overrides.
