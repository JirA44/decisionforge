$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Environnement absent. Exécutez d'abord .\scripts\Setup-DecisionForge.ps1"
}

Set-Location $ProjectRoot
& $Python -m pytest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python -m compileall -q src tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Tests et compilation DecisionForge V1.07 : OK"
