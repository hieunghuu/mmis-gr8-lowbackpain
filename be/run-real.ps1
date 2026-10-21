$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repoRoot "pipeline\.venv-tss\Scripts\python.exe"
$models = Join-Path $repoRoot "be\data\models"
$runtime = Join-Path $repoRoot "be\data\live"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Khong tim thay moi truong AI: $python"
}

$env:MOCK_WORKER = "0"
$env:TOTALSPINESEG_DATA = $models
$env:DATA_DIR = $runtime
$env:DATABASE_PATH = Join-Path $runtime "app.db"
$env:JOB_TIMEOUT_SEC = if ($env:JOB_TIMEOUT_SEC) { $env:JOB_TIMEOUT_SEC } else { "1800" }
$env:SERVE_FRONTEND = if ($env:SERVE_FRONTEND) { $env:SERVE_FRONTEND } else { "1" }

Set-Location $repoRoot
& $python -m uvicorn be.app.main:app --host 0.0.0.0 --port 8000 --workers 1
