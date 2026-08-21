$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

foreach ($Command in @("node", "npm", "python")) {
  if (!(Get-Command $Command -ErrorAction SilentlyContinue)) {
    throw "$Command bulunamadı. Node.js 22+ ve Python 3.12+ kurulu olmalıdır."
  }
}

Write-Host "OPEX Inventory V21 bağımlılıkları kuruluyor..." -ForegroundColor Cyan
Set-Location $ProjectRoot
npm install

if ($LASTEXITCODE -ne 0) {
  throw "npm install başarısız oldu."
}

Write-Host "OPEX Inventory V21 başlatılıyor..." -ForegroundColor Green
npm run dev
