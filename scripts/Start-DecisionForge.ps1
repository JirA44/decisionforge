$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Environnement absent. Exécutez d'abord .\scripts\Setup-DecisionForge.ps1"
}

Set-Location $ProjectRoot
& $Python -m uvicorn decisionforge.api:app --host 127.0.0.1 --port 8014
