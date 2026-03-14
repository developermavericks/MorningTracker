---
phase: 2
plan: 1
wave: 1
---

# Plan 2.1: Run a test scrape and capture logs

## Objective
Restart the backend and run a fresh scrape job to confirm the cumulative and phase-specific logs are working.

## Context
- `backend/scraper/engine.py`: Implementation of logs.

## Tasks

<task type="auto">
  <name>Restart Backend</name>
  <files>backend/main.py</files>
  <action>
    - Terminate current `uvicorn` process.
    - Start a new `uvicorn` instance.
  </action>
</task>

<task type="auto">
  <name>Trigger Test Scrape</name>
  <files>backend/trigger_and_export.py</files>
  <action>
    - Trigger a new scrape job for the AI sector in India.
  </action>
</task>

<task type="auto">
  <name>Verify Logs</name>
  <files>backend/scraper.log</files>
  <action>
    - Wait and check the logs for:
      "SCRAPER: Cumulative unique URLs discovered: {N}"
      "SCRAPER: Phase Discovery progress: {M} unique URLs found so far..."
  </action>
  <verify>Logs contain the expected format.</verify>
  <done>Log entries are verified in the captured output.</done>
</task>

## Success Criteria
- [ ] Multiple phases output distinct cumulative vs per-phase counts.
- [ ] Cumulative count is non-decreasing.
