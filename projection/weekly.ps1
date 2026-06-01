# weekly.ps1 — one-command Friday workflow.
#
# Usage:
#   .\weekly.ps1                    # uses today's date
#   .\weekly.ps1 -Date 2026-05-15   # use a specific date
#   .\weekly.ps1 -SkipPrompt        # don't pause for file drop (files already in place)
#
# What it does:
#   1. Computes the snapshot date (today, unless -Date supplied).
#   2. Creates raw/<date>/ if missing and opens it in Explorer.
#   3. Pauses for you to drop the 25 CCS files in (unless -SkipPrompt).
#   4. Runs the pipeline (ingest -> projections -> velocity -> dashboard).
#   5. Reports any pending calibrations (cohorts past start date without actuals).
#   6. Opens dashboard/index.html in your default browser.

param(
    [string]$Date = (Get-Date -Format "yyyy-MM-dd"),
    [switch]$SkipPrompt
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

$rawDir = Join-Path $root "raw\$Date"
if (-not (Test-Path $rawDir)) {
    New-Item -ItemType Directory -Path $rawDir | Out-Null
    Write-Host "Created $rawDir" -ForegroundColor Green
} else {
    Write-Host "Reusing existing $rawDir" -ForegroundColor Yellow
}

if (-not $SkipPrompt) {
    Write-Host ""
    Write-Host "Opening $rawDir in Explorer." -ForegroundColor Cyan
    Write-Host "Drop EnrollList.csv there (or the legacy 25 per-cohort CCS files), then press Enter."
    Start-Process explorer.exe $rawDir
    Read-Host "Press Enter when files are in place"
}

$csvCount = (Get-ChildItem $rawDir -Filter "*.csv" | Measure-Object).Count
Write-Host ""
Write-Host "Found $csvCount CSV file(s) in $rawDir" -ForegroundColor Cyan
if ($csvCount -eq 0) {
    Write-Host "No CSV files. Aborting." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Running pipeline..." -ForegroundColor Cyan
& uv run python -m scripts.run_pipeline --date $Date
if ($LASTEXITCODE -ne 0) {
    Write-Host "Pipeline failed." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Checking for pending cohort calibrations..." -ForegroundColor Cyan
& uv run python -m scripts.pending_calibrations --as-of $Date

Write-Host ""
Write-Host "Opening dashboard..." -ForegroundColor Cyan
Start-Process (Join-Path $root "dashboard\index.html")
Write-Host "Done." -ForegroundColor Green
