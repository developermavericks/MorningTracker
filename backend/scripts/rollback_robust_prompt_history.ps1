# Rollback Script: Robust Automation Prompt History & Supporting Documents
# This script reverts code changes and provides instructions for DB column/table drop if needed.

Write-Host "==========================================" -ForegroundColor Yellow
Write-Host "Robust Automation Prompt History Rollback" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Yellow

$confirm = Read-Host "Are you sure you want to rollback code changes? (y/n)"
if ($confirm -ne "y") {
    Write-Host "Rollback cancelled." -ForegroundColor Green
    exit
}

Write-Host "`n1. Database Schema Cleanup Instructions:" -ForegroundColor Cyan
Write-Host "The new columns in 'robust_companies' and the 'robust_prompt_histories' table are backward-compatible."
Write-Host "If you strictly want to drop them from PostgreSQL or SQLite:"
Write-Host "--------------------------------------------------" -ForegroundColor DarkGray
Write-Host "ALTER TABLE robust_companies DROP COLUMN IF EXISTS verification_doc_filename;"
Write-Host "ALTER TABLE robust_companies DROP COLUMN IF EXISTS verification_doc_text;"
Write-Host "ALTER TABLE robust_companies DROP COLUMN IF EXISTS verification_system_prompt;"
Write-Host "ALTER TABLE robust_companies DROP COLUMN IF EXISTS verification_user_prompt;"
Write-Host "ALTER TABLE robust_companies DROP COLUMN IF EXISTS summary_user_prompt;"
Write-Host "ALTER TABLE robust_companies DROP COLUMN IF EXISTS executive_user_prompt;"
Write-Host "DROP TABLE IF EXISTS robust_prompt_histories;"
Write-Host "--------------------------------------------------" -ForegroundColor DarkGray

Write-Host "`n2. Rollback complete." -ForegroundColor Green
