$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Installer = Join-Path $ProjectRoot "INSTALL_DOCKOS_RC75_FULLSTACK.ps1"

if (!(Test-Path $Installer)) {
  throw "Ana kurulum dosyasi bulunamadi: $Installer"
}

Set-ExecutionPolicy -Scope Process Bypass -Force
Write-Host "OPEX Workforce V9 kurulumu baslatiliyor..." -ForegroundColor Cyan
& $Installer
Write-Host "Kurulum tamamlandi. Baslatmak icin: .\START_OPEX_WORKFORCE.ps1" -ForegroundColor Green
