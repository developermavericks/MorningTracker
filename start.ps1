$ErrorActionPreference = "Stop"

$pythonExe = "python"
if (Test-Path "backend\venv\Scripts\python.exe") {
    $pythonExe = "backend\venv\Scripts\python.exe"
}

Write-Host "Booting NEXUS Launcher..." -ForegroundColor Cyan
& $pythonExe "start.py"
