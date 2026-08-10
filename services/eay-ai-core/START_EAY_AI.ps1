$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

foreach ($Command in @("python", "ollama")) {
  if (!(Get-Command $Command -ErrorAction SilentlyContinue)) {
    throw "$Command bulunamadi. Python 3.11+ ve Ollama kurulu olmalidir."
  }
}

if (!(Test-Path ".venv")) {
  Write-Host "EAY AI Python ortami olusturuluyor..." -ForegroundColor Cyan
  python -m venv .venv
}

& ".\.venv\Scripts\Activate.ps1"
python -m pip install -U pip
pip install -e ".[dev]"

if (!(Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
}

$ModelExists = ollama list | Select-String -SimpleMatch "eay-ops:0.1"
if (-not $ModelExists) {
  Write-Host "EAY-Ops local model olusturuluyor..." -ForegroundColor Cyan
  ollama pull qwen3:8b
  ollama create eay-ops:0.1 -f ".\models\EAY-Ops.Modelfile"
}

Write-Host "EAY AI Core:           http://127.0.0.1:8010" -ForegroundColor Green
Write-Host "Swagger:               http://127.0.0.1:8010/docs" -ForegroundColor Green
Write-Host "Regulatory sources:    http://127.0.0.1:8010/v1/regulatory/sources" -ForegroundColor Green
Write-Host "Regulatory check POST: http://127.0.0.1:8010/v1/regulatory/check" -ForegroundColor Green
Write-Host "Legal instruments:     http://127.0.0.1:8010/v1/legal/instruments" -ForegroundColor Green
Write-Host "Company-law conflicts: http://127.0.0.1:8010/v1/legal/conflicts" -ForegroundColor Green
uvicorn app.entrypoint:app --host 127.0.0.1 --port 8010 --reload
