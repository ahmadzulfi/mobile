# Menjalankan Macaroni Holic POS di komputer (mode desktop).
# Pemakaian:  .\run.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Membuat .venv ..."
    python -m venv .venv
}

& .venv\Scripts\python.exe -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('flet') else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Memasang Flet (sekali saja, butuh beberapa menit) ..."
    & .venv\Scripts\python.exe -m pip install "flet[all]==1.1.3"
}

Write-Host "Membuka aplikasi ..."
& .venv\Scripts\flet.exe run src\main.py
