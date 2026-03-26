# Nexus Local Launcher (Windows PowerShell)

Write-Host "=== Starting NEXUS Local System ===" -ForegroundColor Cyan

# 1. Load Environment Variables from .env.local
if (Test-Path "backend/.env.local") {
    Write-Host "Loading environment from .env.local..."
    Get-Content "backend/.env.local" | Where-Object { $_ -match '=' } | ForEach-Object {
        $name, $value = $_.Split('=', 2)
        [System.Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim(), "Process")
    }
}

# 2. Check for Redis (Assuming Docker Desktop is running or local redis-server)
Write-Host "Checking for Redis connectivity..."
# Simple check using python
python -c "import redis; r=redis.Redis(host='127.0.0.1', port=6379); print('Redis OK') if r.ping() else exit(1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Redis is not reachable on localhost:6379. Please start Redis." -ForegroundColor Red
    exit
}

# 3. Initialize Database
Write-Host "Initializing Database schema..."
python run_init_db.py

# 4. Start Celery Worker (New Window)
Write-Host "Starting Celery Worker..."
$worker_cmd = "cd backend; $env:CELERY_WORKER_GEVENT=1; celery -A celery_app worker --loglevel=info -P gevent --concurrency=16"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "$worker_cmd"

# 5. Start FastAPI Backend
Write-Host "Starting FastAPI Backend..."
$backend_cmd = "cd backend; uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "$backend_cmd"

Write-Host "System started! Backend: http://localhost:8000" -ForegroundColor Green
Write-Host "Restructuring Complete. Ready for Testing." -ForegroundColor Cyan
