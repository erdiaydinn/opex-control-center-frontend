$ErrorActionPreference = "Continue"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$target = Join-Path $ProjectRoot "test-artifacts\diagnostics-$stamp"
$zipPath = "$target.zip"
New-Item -ItemType Directory -Force -Path $target | Out-Null

function Save-Command([string]$Name, [scriptblock]$Command) {
  try { & $Command 2>&1 | Out-File (Join-Path $target $Name) -Encoding UTF8 -Width 240 }
  catch { $_ | Out-String | Out-File (Join-Path $target $Name) -Encoding UTF8 }
}

Push-Location $ProjectRoot
try {
  Save-Command "docker-version.txt" { docker version }
  Save-Command "compose-version.txt" { docker compose version }
  Save-Command "compose-ps.txt" { docker compose ps }
  Save-Command "compose-images.txt" { docker compose images }
  Save-Command "backend-logs.txt" { docker compose logs --since 60m --no-color backend }
  Save-Command "frontend-logs.txt" { docker compose logs --since 60m --no-color frontend }
  Save-Command "postgres-logs.txt" { docker compose logs --since 60m --no-color postgres }
  Save-Command "backup-logs.txt" { docker compose logs --since 60m --no-color backup }
  Save-Command "health.txt" { Invoke-RestMethod "http://127.0.0.1:8000/api/workforce/health" -TimeoutSec 10 | ConvertTo-Json -Depth 5 }
  Save-Command "disk.txt" { Get-PSDrive -PSProvider FileSystem | Select-Object Name, Used, Free, Root | Format-Table -AutoSize }
} finally {
  Pop-Location
}

$safeConfig = @()
$envFile = Join-Path $ProjectRoot ".env"
if (Test-Path $envFile) {
  foreach ($name in @("DOCKOS_ENV", "OPEX_ALLOW_LEGACY_HEADERS", "VITE_LOCAL_PILOT_MODE", "OPEX_ATTESTATION_MODE", "POSTGRES_DB", "POSTGRES_USER")) {
    $line = Get-Content $envFile | Where-Object { $_ -match "^$([Regex]::Escape($name))=" } | Select-Object -First 1
    $safeConfig += if ($line) { $line } else { "$name=<missing>" }
  }
}
$safeConfig | Set-Content (Join-Path $target "safe-config.txt") -Encoding UTF8

@"
Olusturma: $(Get-Date -Format o)
Not: .env, TC/personel tablolari, APNs veya Google anahtarlari bu pakete alinmaz.
Docker loglarinda operasyonel request id ve hata metni bulunabilir; paylasmadan once kontrol edin.
"@ | Set-Content (Join-Path $target "README.txt") -Encoding UTF8

Compress-Archive -Path "$target\*" -DestinationPath $zipPath -CompressionLevel Optimal -Force
Write-Host "Teshis paketi hazir: $zipPath" -ForegroundColor Green
