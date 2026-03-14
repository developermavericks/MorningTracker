# SPEC.md — Distributed Systems Transformation (Phase 6)

> **Status**: `DRAFT`
>
> ⚠️ **Planning Lock**: No code may be written until this spec is marked `FINALIZED`.

## Vision
Enhance the scraper engine and dashboard to provide real-time metrics on URL discovery (Discovery Pool) and granular task tracking (Phase Status) to improve transparency for long-running jobs.

## Goals
1. **Database Modernization** — Move from SQLite to PostgreSQL + SQLAlchemy (Async) with JSONB for metadata flexibility.
2. **Asynchronous Decoupling** — Implement Celery chaining: `scrape_node` (I/O) $\rightarrow$ `enrich_node` (Compute/AI).
3. **Frontend API Layer** — Implement centralized Axios client with 401 interceptors and Zustand for global job tracking.

## Success Criteria
- [ ] No `BackgroundTasks` used; all enrichment is handled via Celery.
- [ ] Database URL points to PostgreSQL; migrations handled via ORM.
- [ ] Scraping and AI enrichment are separate Celery tasks with independent retry logic.
- [ ] Frontend uses `api.js` wrapper with centralized auth management.

---
*Last updated: 2026-03-04*
