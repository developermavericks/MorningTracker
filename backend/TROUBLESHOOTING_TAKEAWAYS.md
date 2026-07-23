# Operational Runbook: Monthly Strategic Takeaways Tracker & Scheduler

This runbook helps developers and system admins troubleshoot, monitor, and configure the automated daily takeaways sheet updater and the scheduled monthly email dispatcher.

---

## 1. Feature Architecture

The takeaways scheduler consists of three core components:
1. **Daily Parser & Appender:** Inside `run_heavy_automation_task`, after the LLM extracts key bullet points, the worker calls `append_daily_takeaways_to_sheet`. This function searches Drive for the company spreadsheet `"{company_name} - Strategic Takeaways History"`, downloads it, opens it via `openpyxl`, updates/creates a tab for the current month (e.g. `"July 2026"`), appends a styled row for each bullet point, and uploads it back to Google Drive.
2. **Monthly Schedule Evaluator:** In `check_heavy_automation_schedules` (Celery Beat task), it checks if any company is configured to send monthly reports (`send_monthly_takeaways_enabled = True`). If current local time matches the designated day/time and it hasn't run yet this month, it sends the task `send_monthly_takeaways_report_task` to the worker.
3. **Monthly Email Dispatcher:** The Celery task downloads the Excel file from Google Drive, emails it as an attachment to all brand recipients, and updates the `last_monthly_takeaways_sent_at` timestamp.

---

## 2. Diagnostics Tooling

A production diagnostics script is located in:
```bash
python scripts/diagnose_takeaways_scheduler.py
```
Run this script inside your backend environment to automatically verify:
* Database schema column existence.
* List of companies in the DB and their takeaways parameters.
* Google Drive API credential loading and scope connection check.
* SMTP credentials configurations.

---

## 3. Database Management (SQL Cheat Sheet)

Use these SQL commands to debug configurations or check status:

### Inspect Active Takeaways Schedulers
```sql
SELECT id, name, enabled, takeaways_sheet_url, send_monthly_takeaways_enabled, monthly_takeaways_day, monthly_takeaways_time, last_monthly_takeaways_sent_at 
FROM heavy_companies 
WHERE enabled = true;
```

### Enable/Configure Schedulers Manually
```sql
UPDATE heavy_companies 
SET send_monthly_takeaways_enabled = true,
    monthly_takeaways_day = 1,
    monthly_takeaways_time = '09:00'
WHERE name = 'Google';
```

### Reset Sent Timestamp to Re-trigger Month's Run
```sql
UPDATE heavy_companies 
SET last_monthly_takeaways_sent_at = NULL 
WHERE name = 'Google';
```

---

## 4. Common Failure Modes & Troubleshooting

### Case A: "Google Drive service not initialized" or Upload Errors
* **Symptoms:** Logs contain `[Takeaways Sheet] Google Drive service not initialized` or `Failed to upload takeaways sheet`.
* **Checks:**
  1. Ensure either the `GOOGLE_CREDENTIALS_JSON` environment variable is correctly set in Railway/`.env` or that `google_credentials.json` exists in the `backend` directory.
  2. Verify credentials contain authorized scopes for:
     * `https://www.googleapis.com/auth/drive`
     * `https://www.googleapis.com/auth/documents`
  3. Ensure the service account has permission to write inside the folders configured for the client.

### Case B: Monthly Report email not sending at scheduled time
* **Symptoms:** Scheduled time passes but recipients do not receive the email, and `last_monthly_takeaways_sent_at` is not updated.
* **Checks:**
  1. **Timezone discrepancies:** The scheduler evaluates the trigger in the company's local timezone. Ensure `timezone` on the company record matches the user expectation (e.g. `Asia/Kolkata` or `UTC`).
  2. **Celery Beat status:** Check that the Celery Beat scheduler is running. If Celery Beat is down, `check_heavy_automation_schedules` will not run every 5 minutes.
  3. **Daily check block:** Ensure the monthly checks are not skipped. (Our design decouples daily schedules from monthly schedules so they execute independently).

### Case C: Openpyxl local path or download crashes
* **Symptoms:** Worker logs show `[Takeaways Sheet] Error updating Google Sheet... NameError` or `PermissionError`.
* **Checks:**
  1. The code creates a local workspace path `backend/reports/Takeaways_*.xlsx` for downloading and reading before uploading. Ensure the worker process has read/write filesystem access to `backend/reports/` directory.

---

## 5. Rollback Procedures

If an emergency rollback is required, execute:
```powershell
.\scripts\rollback_monthly_takeaways.ps1
```
This script will instantly restore the Git workspace to commit `cd02ac9` (the clean commit before this feature).
