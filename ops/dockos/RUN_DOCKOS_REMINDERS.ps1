param([string]$AdminEmail = "erdi.aydin@yemeksepeti.com", [string]$ApiBase = "http://127.0.0.1:8000/api/dockos")
$ErrorActionPreference = "Stop"
$headers = @{"X-OPEX-User"=$AdminEmail;"X-OPEX-Role"="admin"}
$result = Invoke-RestMethod "$ApiBase/notifications/process-due" -Method Post -Headers $headers -TimeoutSec 30
Write-Host "DockOS notifications: sent=$($result.sent), waiting=$($result.waiting_config), failed=$($result.failed)"
