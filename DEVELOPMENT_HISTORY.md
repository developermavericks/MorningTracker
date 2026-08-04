# Project Development & Deployment History: NEXUS Intelligence Tracker

This document logs all development history, release details, database schema changes, and operational deployments for the NEXUS News Intelligence and Heavy Automation platform.

---

## 1. Release & Deployment Timeline

The following table tracks active commits, implementation authors, change summaries, and their production deployment status on Railway.

| Date & Time (IST) | Commit Hash | Author | Scope / Feature Area | Deployment Status |
| :--- | :--- | :--- | :--- | :--- |
| 2026-08-04 09:14 | `b56b724` | Antigravity | **Config:** Updated Nexus feed server base IP address from `35.240.197.209` to `34.142.240.96`. | Completed & Local |
| 2026-08-03 11:05 | `7aac7be` | Antigravity | **Scraper:** Added Autocar, Autocar Professional, Bike India, Overdrive, PowerDrift, and Zigwheels to Category A publications. | Completed & Tested |
| 2026-07-30 12:32 | `98572da` | Antigravity | **Mailer:** Commented out sending Google Doc links in emails. | Deployed & Active |
| 2026-07-27 16:22 | `818bd82` | Antigravity | **Asset:** Removed static logo to test fallback template compilation. | Deployed & Active |
| 2026-07-24 09:47 | `64b546a` | Antigravity | **Fix:** Resolved `NameError: name 'Any' is not defined` when importing `utils.google_docs` by importing `Any` and `Optional` from `typing`. | Deployed & Active |
| 2026-07-23 15:00 | `f28a99b` | Divyansh Sharma | **Asset:** Updated system fallback Word template (`client_1_template.docx`) with the new Scapia design theme. | Deployed & Active |
| 2026-07-23 14:20 | `e5bc244` | Divyansh Sharma | **Feature:** Added monthly takeaways Excel email scheduling inputs to the Schedule tab in frontend settings UI. | Deployed & Active |
| 2026-07-23 14:15 | `7a13918` | Divyansh Sharma | **Fix & Feature:** Added mailer doc binary database storage backup, and added the "Cumulative Spreadsheet" button to Heavy Automation runs history UI. | Deployed & Active |
| 2026-07-23 13:30 | `c846a42` | Divyansh Sharma | **Fix:** Made takeaways schedule Pydantic response schema robust to prevent validation failures on existing database entries. | Deployed & Active |
| 2026-07-23 12:11 | `bb15e59` | Divyansh Sharma | **Operations:** Added troubleshooting runbook, diagnostic health check python script, and PowerShell rollback recipes. | Deployed & Active |
| 2026-07-23 12:02 | `c357c20` | Divyansh Sharma | **Feature:** Implemented automated monthly strategic takeaways Google Sheet tracking, tabbed openpyxl Excel generators, and Celery scheduler triggers. | Deployed & Active |
| 2026-07-23 11:30 | `cd02ac9` | Divyansh Sharma | **Mailer:** Separated Google and competitor article categories, isolated crisis/spokesperson scopes, and replaced footer with "THE MAVERICKS Intelligence Desk". | Deployed & Active |
| 2026-07-22 18:58 | `e576f84` | Divyansh Sharma | **Mailer:** Cross-publication deduplication, Google ordering hierarchy, 15-word bullet constraints, and extended brand scopes. | Deployed & Active |
| 2026-07-22 17:28 | `7e2cd51` | Divyansh Sharma | **AI Engine:** Restructured Claude prompt guidelines to enforce exactly 4-5 points of maximum 1-2 lines each. | Deployed & Active |
| 2026-07-22 17:03 | `db69bc8` | Divyansh Sharma | **Scraper:** Added production sector match rules: fintech, automobile, media/entertainment, and education. | Deployed & Active |
| 2026-07-22 16:45 | `363be89` | Divyansh Sharma | **Mailer:** Segregated Google/Competition/Industry news briefs and removed legacy takeaways from email layouts. | Deployed & Active |
| 2026-07-22 16:14 | `44a131e` | Divyansh Sharma | **AI Engine:** Added togglable LLM judge and Claude validator modules for advanced article relevance parsing. | Deployed & Active |
| 2026-07-22 13:18 | `6cdb12c` | Divyansh Sharma | **Filtering:** Updated priority filters with regex boundary checks and deterministic section sorting rules. | Deployed & Active |
| 2026-07-20 10:19 | `ed2cf29` | Divyansh Sharma | **Worker:** Overwrite local templates from database cache on worker startup to prevent rendering outdated styles. | Deployed & Active |
| 2026-07-16 10:46 | `3729bf1 | Divyansh Sharma | **Worker:** Added automatic template fallback restorers from DB cache. | Deployed & Active |
| 2026-07-15 16:14 | `442c5b5` | Divyansh Sharma | **Deduplication:** Implemented section-level article deduplication by canonical URL matching. | Deployed & Active |
| 2026-07-15 11:23 | `54c7722` | Divyansh Sharma | **Database:** Added cumulative sheet URL schema updates for async SQL initializers. | Deployed & Active |

---

## 2. Major Development Phases Detailed

### Phase A: Mailer Restructuring & AI-Judgement (July 15 - July 22, 2026)
* **Relevancy Scoring Toggles:** Integrated LLM Relevance Judge checks that can be enabled/disabled dynamically per company in the admin console.
* **Format Constraints:** Restricted AI-generated executive summaries to exactly 4-5 points of maximum 1-2 lines each to maintain standard briefing sizing.
* **Sector Additions:** Expanded database parsing matrices to support fintech, automobile, media, and education sector filters.

### Phase B: Google Filtering & Sign-off Rebranding (July 23, 2026)
* **Samsung & Competitor Filtering:** Isolated competitor keyword occurrences (`is_competitor` check aggregated over Apple, Samsung, OpenAI, Meta, Microsoft, Amazon, Perplexity, Anthropic, Paytm, and MapMyIndia) to prevent competitor news from rendering in the Google section.
* **Separated Crisis and Spokespersons:** Guaranteed that spokesperson and crisis sections under the Competition heading only match competitor-branded stories, leaving direct Google crises isolated.
* **Rebranding Signature:** Hardcoded the footer to read `"THE MAVERICKS Intelligence Desk"`.

### Phase C: Monthly Strategic Takeaways Sheet Tracker & Scheduler (July 23, 2026)
* **Openpyxl Tabbed Spreadsheets:** Appends daily strategic takeaways to a spreadsheet titled `"{company_name} - Strategic Takeaways History"` inside Google Drive. Each month is separated dynamically into a tab named after the current month (e.g. `"July 2026"`).
* **Dual-Schedule Beat Runner:** Refactored the Celery Beat scheduler checking loop to run Section A (daily scrapers) and Section B (monthly takeaways scheduler check) independently.
* **REST API Settings:** Added schema options for monthly takeaways scheduling (`enabled`, `day`, `time`) and exposed a private `GET /companies/{company_id}/takeaways-link` endpoint for admin dashboard downloads.

---

## 3. Production Deployment Notes (Railway)

* **Schema Migrations:** The backend leverages dynamic startup schema detection inside `init_db_sync()`. During Railway deployments, the container executes migrations automatically on startup, ensuring new configuration columns are added safely.
* **Celery Workers & Beat:** Ensure both Celery Workers and Celery Beat schedule managers are restarted to register the new `scraper.tasks.send_monthly_takeaways_report_task` queue configuration.
