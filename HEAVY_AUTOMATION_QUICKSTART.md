# Heavy Automation — Quick Start Guide

**5-minute local setup | Complete end-to-end test**

---

## ⚡ Local Development (5 min)

### Prerequisites
- Python 3.8+
- Node.js 16+
- `.env` file with `GROQ_API_KEY`, `SMTP_*`

### Step 1: Backend Setup (Terminal 1)
```bash
cd backend

# Initialize database
python run_init_db.py

# Start FastAPI
uvicorn main:app --reload --port 8000
```
**Expected:** `Uvicorn running on http://127.0.0.1:8000`

### Step 2: Celery Worker (Terminal 2)
```bash
cd backend
celery -A celery_app worker --queues reports -l info
```
**Expected:** `Worker ready to accept tasks`

### Step 3: Celery Beat (Terminal 3)
```bash
cd backend
celery -A celery_app beat -l info
```
**Expected:** `Scheduler started`

### Step 4: Frontend (Terminal 4)
```bash
cd frontend
npm run dev
```
**Expected:** `Local: http://localhost:5173`

---

## 🧪 End-to-End Test (2 min)

### 1. Login
```
Browser: http://localhost:5173
Email: admin@test.com
Password: admin_pass_123
```

### 2. Create Company
1. Click **Heavy Automation** tab (🔬 icon)
2. Click **+ Add Company**
3. Fill in:
   ```
   Name: Test Company Google
   Sector: google
   Fetch Time: 07:00
   Timezone: Asia/Kolkata
   Relevancy Method: Hybrid
   Threshold: 0.5
   Recipients: your-email@example.com (brief)
   ```
4. Click **Create**

### 3. Trigger Run
1. Click **▶ Run Now** button
2. Switch to **Run History** tab
3. Watch progress (6-sec poll):
   - `status: running`
   - `Fetched 450 articles...`
   - `After dedup: 280 articles...`
   - `Email sent`

### 4. Verify Results
1. Check email inbox for daily briefing
2. Download **Master Report** DOCX
3. Download **Filtered Report** DOCX
4. View **Run History** with article counts

---

## 🔍 API Testing (via curl)

### Get Auth Token
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@test.com","password":"admin_pass_123"}'
# Copy token from response
```

### List Companies
```bash
TOKEN="your-token-here"
curl http://localhost:8000/api/heavy-automation/companies \
  -H "Authorization: Bearer $TOKEN"
```

### Create Company (API)
```bash
curl -X POST http://localhost:8000/api/heavy-automation/companies \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Google India",
    "sector_match": "google",
    "enabled": true,
    "timezone": "Asia/Kolkata",
    "fetch_time": "07:00",
    "window_hours": 24,
    "relevancy_method": "Hybrid",
    "relevance_context": "India-focused news",
    "relevance_threshold": 0.5,
    "mail_send_mode": "Immediate",
    "frequency": "Daily",
    "recipients": [
      {"email":"test@example.com","role":"brief"}
    ]
  }'
```

### Trigger Run
```bash
curl -X POST http://localhost:8000/api/heavy-automation/companies/1/run \
  -H "Authorization: Bearer $TOKEN"
```

### Get Run History
```bash
curl http://localhost:8000/api/heavy-automation/companies/1/runs \
  -H "Authorization: Bearer $TOKEN"
```

### Threshold Preview
```bash
curl -X POST http://localhost:8000/api/heavy-automation/companies/1/preview \
  -H "Authorization: Bearer $TOKEN"
# Shows article counts at thresholds: 0.2, 0.35, 0.5, 0.65, 0.8
```

---

## 📊 What to Expect

| Metric | Value |
|--------|-------|
| Fetch time | 2–5 sec |
| Dedup time | 1–3 sec |
| Filter time | 2–5 sec |
| LLM time | 5–10 sec (optional) |
| Report generation | 5 sec |
| Email send | 2 sec |
| **Total run time** | **20–35 sec** |
| **Cost** | **~$0.05** |
| Articles fetched | 450 (typical) |
| After dedup | 280 (62%) |
| Relevant (filtered) | 125–175 (depends on threshold) |

---

## 🐛 Troubleshooting

### Backend won't start
```bash
# Check port 8000 not in use
lsof -i :8000
# If in use, kill process or use different port:
uvicorn main:app --reload --port 8001
```

### Celery worker won't accept tasks
```bash
# Check Redis/SQLite broker
celery -A celery_app inspect ping
# Check active tasks
celery -A celery_app inspect active
```

### Email not sending
```bash
# Verify SMTP credentials in .env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SENDER_EMAIL=your-email@gmail.com
```

### LLM not running
```bash
# Check Groq API key
echo $GROQ_API_KEY
# Falls back to keyword-only mode if key missing (no crash)
```

### Frontend can't connect to backend
```bash
# Check VITE_API_URL in frontend/.env
VITE_API_URL=http://localhost:8000
# Or set at runtime:
npm run dev -- --env.VITE_API_URL=http://localhost:8000
```

---

## 📖 Documentation

- **Full summary:** `HEAVY_AUTOMATION_SUMMARY.md`
- **Deployment guide:** `HEAVY_AUTOMATION_DEPLOYMENT.md`
- **Code:** `backend/scraper/heavy_*.py`, `backend/routers/heavy_automation.py`, `frontend/HeavyAutomation.jsx`

---

## ✨ Next Steps

1. **Test locally** (this guide)
2. **Verify DOCX quality** (download a Master Report)
3. **Check email delivery** (confirm briefing email arrives)
4. **Deploy to Railway + Vercel** (HEAVY_AUTOMATION_DEPLOYMENT.md)
5. **Monitor first 3 runs** (check logs, email delivery, costs)

---

**Status:** Ready to ship! 🚀

---

**Need help?** Check logs in Terminal 2 (Worker) or Terminal 3 (Beat) for detailed error messages.
