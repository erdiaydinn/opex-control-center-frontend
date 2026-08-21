$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "OPEX Inventory V24 kuruluyor..." -ForegroundColor Cyan
& (Join-Path $ProjectRoot "INSTALL_DOCKOS_RC75_FULLSTACK.ps1")

Write-Host "V24 kurulumu tamamlandi." -ForegroundColor Green
Write-Host "Baslatmak icin: .\START_OPEX_INVENTORY_V24.ps1" -ForegroundColor Yellow
