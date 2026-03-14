---
phase: 1
plan: 1
wave: 1
---

# Plan 1.1: Database and Engine Set Initialization

## Objective
Update the `discover_articles` function to track cumulative unique URLs across all discovery phases of a single job and update the log output.

## Context
- `backend/scraper/engine.py`: Core discovery and logging logic.

## Tasks

<task type="auto">
  <name>Modify discover_articles signature and logic</name>
  <files>backend/scraper/engine.py</files>
  <action>
    - Add `cumulative_seen` set as an optional parameter to `discover_articles`.
    - If `cumulative_seen` is provided, add all newly discovered URLs to it.
    - Update the log line at line 321 to show both the collective total and the current phase count.
  </action>
  <verify>Check if the function signature and logging were updated.</verify>
  <done>The function now and its log line reflect the cumulative and per-phase counts.</done>
</task>

<task type="auto">
  <name>Update run_scrape_job to maintain the cumulative set</name>
  <files>backend/scraper/engine.py</files>
  <action>
    - Initialize an empty `cumulative_seen` set at the start of `run_scrape_job`.
    - Pass this set to any calls to `discover_articles`.
    - Use the length of this set for the final `total_found` database update.
  </action>
</task>

## Success Criteria
- [ ] Log output now includes both totals.
- [ ] Discovery logic correctly uses the shared set.
