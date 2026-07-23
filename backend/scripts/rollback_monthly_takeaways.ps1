# Rollback Script: Monthly Takeaways Feature
# This script reverts the git branch to the commit before the feature implementation and offers instructions for DB rollbacks.

Write-Host "==========================================" -ForegroundColor Yellow
Write-Host "Monthly Takeaways Feature Rollback Script" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Yellow

$confirm = Read-Host "Are you sure you want to rollback all code changes? (y/n)"
if ($confirm -ne "y") {
    Write-Host "Rollback cancelled." -ForegroundColor Green
    exit
}

# The stable commit before this feature was implemented
$PreFeatureCommit = "cd02ac9f71c4c1a2f6460f701c9f69ad9f92adbe"

Write-Host "`n1. Reverting local Git tree to $PreFeatureCommit..." -ForegroundColor Cyan
git reset --hard $PreFeatureCommit

Write-Host "`n2. Database Schema Rollback Guide:" -ForegroundColor Cyan
Write-Host "The new columns added to 'heavy_companies' are backward-compatible and safe to leave in the database."
Write-Host "If you strictly want to drop them to reclaim schema state:"
Write-Host "Run the following SQL commands on your database client (Postgres or SQLite):"
Write-Host "--------------------------------------------------" -ForegroundColor DarkGray
Write-Host "ALTER TABLE heavy_companies DROP COLUMN IF EXISTS takeaways_sheet_url;"
Write-Host "ALTER TABLE heavy_companies DROP COLUMN IF EXISTS send_monthly_takeaways_enabled;"
Write-Host "ALTER TABLE heavy_companies DROP COLUMN IF EXISTS monthly_takeaways_day;"
Write-Host "ALTER TABLE heavy_companies DROP COLUMN IF EXISTS monthly_takeaways_time;"
Write-Host "ALTER TABLE heavy_companies DROP COLUMN IF EXISTS last_monthly_takeaways_sent_at;"
Write-Host "--------------------------------------------------" -ForegroundColor DarkGray

Write-Host "`n3. Re-initialize local database..." -ForegroundColor Cyan
python init_db.py

Write-Host "`n4. Force pushing changes to remote origin..." -ForegroundColor Cyan
Write-Host "If you want to push this rollback to GitHub, run:"
Write-Host "  git push origin its_Divs_current_new_testing_updates --force" -ForegroundColor Yellow

Write-Host "`n[SUCCESS] Rollback actions complete. Local codebase has been restored to stable state." -ForegroundColor Green
