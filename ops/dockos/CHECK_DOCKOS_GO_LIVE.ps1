param([string]$ApiBase = "http://127.0.0.1:8000/api")
$ErrorActionPreference = "Stop"
$health = Invoke-RestMethod "$ApiBase/dockos/health" -TimeoutSec 15
Write-Host "Release: $($health.release)" -ForegroundColor Cyan
$result = Invoke-RestMethod "$ApiBase/dockos/readiness" -TimeoutSec 15
foreach ($check in $result.checks) {
  if ($check.ok) {
    Write-Host "OK   $($check.key) - $($check.detail)" -ForegroundColor Green
  } else {
    Write-Host "FAIL $($check.key) - $($check.detail)" -ForegroundColor Red
  }
}
if (!$result.ready) {
  throw "DockOS canli yayin kapisi KAPALI. FAIL maddelerini tamamlayin."
}
Write-Host "DockOS canli yayin kapisi ACIK." -ForegroundColor Green
