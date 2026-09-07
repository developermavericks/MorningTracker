# NEXUS Deployment Status & Hardening Checklist

This document is the **authoritative production pre-flight checklist** for the NEXUS News Intelligence and Automation Platform. 

Every time code changes are introduced, this checklist **MUST be checked and validated** before pushing commits to GitHub and deploying to **Railway** (Backend, Celery Workers, Database) and **Vercel** (Frontend).

---

## 1. Railway Ephemeral Containers Safeguards

Railway containers use ephemeral filesystems. When a container restarts, rebuilds, or deploys, any files written strictly to container disk (`/tmp`, `./reports`, etc.) are wiped. To prevent crashes and missing file errors:

- [x] **Database BLOB Persistence**: All user-uploaded supporting documents (`verification_doc_data`), keywords Excel files (`keywords_file_data`), and priority media lists (`priority_media_file_data`) MUST be saved as `BYTEA` / `LargeBinary` BLOBs inside PostgreSQL / SQLite.
- [x] **Dynamic Report Restoration**: Report files (`master_doc_data`, `filtered_doc_data`, `master_excel_data`, `filtered_excel_data`, `mailer_doc_data`) MUST be backed up to the database during generation. `GET /reports/{filename}` dynamically restores the file from DB BLOBs if local disk cache is wiped.
- [x] **PDF Extractor Dependency**: `pdfplumber>=0.11.0` and `pypdf>=4.0.0` MUST be declared in [`backend/requirements.txt`](file:///e:/MAVERICKS/zMorning_Tracker_Synced_Git/backend/requirements.txt) so Railway Docker build installs them without `ModuleNotFoundError`.
- [x] **NullPool for Gevent Workers**: Worker services running Celery MUST specify `DB_USE_NULLPOOL=true` in Railway environment variables to prevent asyncpg pool deadlocks on container shutdown.

---

## 2. Pre-Push Verification Checklist

Run these automated verification steps locally before executing `git push`:

### Step A: Schema & Diagnostics Check
Execute the automated diagnostic script from `backend/scripts`:
```powershell
cd backend/scripts
..\venv\Scripts\python.exe diagnose_takeaways_scheduler.py
```
*Expected Output:* `[DIAGNOSTIC STATUS] ALL CHECKS PASSED. Ready for deployment!`

### Step B: Verification of Auth & Query Token Endpoints
Ensure file preview/download endpoints support `?token=...` query string authorization (since HTML `<iframe>` and file downloads do not send `Authorization: Bearer` headers):
- Check [`backend/routers/auth_utils.py`](file:///e:/MAVERICKS/zMorning_Tracker_Synced_Git/backend/routers/auth_utils.py#L105): `get_auth_user` must include `query_token: Optional[str] = Query(None, alias="token")`.
- Test query token authentication locally:
  ```python
  import urllib.request
  token = "YOUR_JWT_TOKEN"
  req = urllib.request.Request(f"http://localhost:8000/api/robust-automation/companies/1/doc/file?token={token}")
  res = urllib.request.urlopen(req)
  assert res.status == 200
  ```

### Step C: Frontend Axios & Form Data Verification
- Do NOT manually set `Content-Type: multipart/form-data` in Axios headers when sending `FormData` objects. Allow Axios and browser to generate `multipart/form-data; boundary=...`.
- Verify Vercel frontend CORS origin is listed in [`backend/main.py`](file:///e:/MAVERICKS/zMorning_Tracker_Synced_Git/backend/main.py) CORS whitelist (`https://morning-tracker-sigma.vercel.app`).

### Step D: Update Change Logs
- [x] Append release entry to [`DEVELOPMENT_HISTORY.md`](file:///e:/MAVERICKS/zMorning_Tracker_Synced_Git/DEVELOPMENT_HISTORY.md) specifying IST timestamp, author, feature scope, and local verification status.

---

## 3. Deployment Checklist Matrix

| Component | Target Host | Key Environment Variables / Settings | Health Check |
| :--- | :--- | :--- | :--- |
| **API Backend** | Railway | `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, `GROQ_API_KEY` | `GET /api/health` -> `{"status":"ok"}` |
| **Celery Worker** | Railway | `DB_USE_NULLPOOL=true`, `REDIS_URL`, `DATABASE_URL` | Logs: `celery worker ready` |
| **Celery Beat** | Railway | `REDIS_URL`, `DATABASE_URL` | Logs: `Beat: Starting...` |
| **Web Frontend** | Vercel | `VITE_API_URL` (points to Railway API URL ending in `/api/`) | Frontend page loads cleanly |

---

## 4. Rollback Recipes

In the event of a deployment issue, execute the targeted PowerShell rollback recipe from `backend/scripts`:

- **Rollback Prompt History / Supporting Doc**:
  ```powershell
  cd backend/scripts
  .\rollback_robust_prompt_history.ps1
  ```
- **Rollback Monthly Takeaways**:
  ```powershell
  cd backend/scripts
  .\rollback_monthly_takeaways.ps1
  ```

---

## 5. Deployment Trigger Policy

- **DO NOT** run `git push` automatically until the explicit trigger phrase `"fuckmylife"` is provided by the user.
- All code edits must be hardened, tested locally, and validated against this document prior to push.
