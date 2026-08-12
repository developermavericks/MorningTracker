# Rollback Script: Polled Sector Categorization Feature
# This script reverts the git branch to the commit before the feature implementation and offers instructions for DB rollbacks.

Write-Host "==========================================" -ForegroundColor Yellow
Write-Host "Polled Sector Categorization Feature Rollback Script" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Yellow

$confirm = Read-Host "Are you sure you want to rollback all code changes? (y/n)"
if ($confirm -ne "y") {
    Write-Host "Rollback cancelled." -ForegroundColor Green
    exit
}

# The stable commit before this feature was implemented
$PreFeatureCommit = "eba54745bc5d1ad034da07600b5ce1d4ee82a762"

Write-Host "`n1. Reverting local Git tree to $PreFeatureCommit..." -ForegroundColor Cyan
git reset --hard $PreFeatureCommit

Write-Host "`n2. Database Schema Rollback Guide:" -ForegroundColor Cyan
Write-Host "The new column added to 'robust_companies' is backward-compatible and safe to leave in the database."
Write-Host "If you strictly want to drop them to reclaim schema state:"
Write-Host "Run the following SQL commands on your database client (Postgres or SQLite):"
Write-Host "--------------------------------------------------" -ForegroundColor DarkGray
Write-Host "ALTER TABLE robust_companies DROP COLUMN IF EXISTS group_by_source_sector;"
Write-Host "--------------------------------------------------" -ForegroundColor DarkGray

Write-Host "`n3. Re-initialize local database..." -ForegroundColor Cyan
python init_db.py

Write-Host "`n4. Code Rollback complete." -ForegroundColor Green
