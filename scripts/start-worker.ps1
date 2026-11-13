$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path ".env")) { throw "Copy .env.example to .env and configure it first." }
if (-not (Test-Path ".venv\Scripts\python.exe")) { throw "Create the virtual environment and install requirements first." }
. .\.venv\Scripts\Activate.ps1
python -m apps.worker
