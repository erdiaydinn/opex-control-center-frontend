param([switch]$PrepareOnly)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function New-Base64Secret([int]$Length = 32) {
  $bytes = New-Object byte[] $Length
  $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try {
    $generator.GetBytes($bytes)
    return [Convert]::ToBase64String($bytes)
  } finally {
    $generator.Dispose()
  }
}

function New-UrlSafeSecret {
  return ([Guid]::NewGuid().ToString("N") + [Guid]::NewGuid().ToString("N"))
}

function Set-DotEnvValue([string]$Content, [string]$Name, [string]$Value) {
  $escapedName = [Regex]::Escape($Name)
  if ($Content -match "(?m)^$escapedName=") {
    return [Regex]::Replace($Content, "(?m)^$escapedName=.*$", "$Name=$Value")
  }
  return $Content.TrimEnd() + "`r`n$Name=$Value`r`n"
}

if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker Desktop bulunamadi. Docker Desktop'i kurup actiktan sonra tekrar deneyin."
}
docker compose version | Out-Null

$EnvFile = Join-Path $ProjectRoot ".env"
if (!(Test-Path $EnvFile)) {
  $templatePath = Join-Path $ProjectRoot ".env.example"
  if (!(Test-Path $templatePath)) { $templatePath = Join-Path $ProjectRoot "ENV_TEMPLATE_V13_2.txt" }
  if (!(Test-Path $templatePath)) { throw "Ortam sablonu bulunamadi (.env.example / ENV_TEMPLATE_V13_2.txt). ZIP'i yeniden cikartin." }
  $template = Get-Content $templatePath -Raw
  $databasePassword = New-UrlSafeSecret
  $template = $template.Replace("CHANGE_ME_AT_LEAST_32_RANDOM_CHARACTERS", (New-Base64Secret 32))
  $template = $template.Replace("CHANGE_ME_RANDOM_DATABASE_PASSWORD", $databasePassword)
  $template = $template.Replace("CHANGE_ME_BASE64_32_BYTE_KEY", (New-Base64Secret 32))
  $template = $template.Replace("CHANGE_ME_GRAFANA_PASSWORD", (New-Base64Secret 24))
  Set-Content -Path $EnvFile -Value $template -Encoding UTF8
} else {
  $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  Copy-Item $EnvFile (Join-Path $ProjectRoot ".env.before-local-pilot-$stamp")
  Write-Host "Mevcut .env yedeklendi: .env.before-local-pilot-$stamp" -ForegroundColor Yellow
}

$content = Get-Content $EnvFile -Raw
$dbUserLine = [Regex]::Match($content, "(?m)^POSTGRES_USER=(.*)$")
$dbPasswordLine = [Regex]::Match($content, "(?m)^POSTGRES_PASSWORD=(.*)$")
$dbNameLine = [Regex]::Match($content, "(?m)^POSTGRES_DB=(.*)$")
if (!$dbUserLine.Success -or !$dbPasswordLine.Success -or !$dbNameLine.Success) { throw "PostgreSQL .env ayarlari eksik." }
$dbUser = $dbUserLine.Groups[1].Value.Trim()
$dbPassword = $dbPasswordLine.Groups[1].Value.Trim()
$dbName = $dbNameLine.Groups[1].Value.Trim()
$encodedPassword = [Uri]::EscapeDataString($dbPassword)
$content = Set-DotEnvValue $content "DATABASE_URL" "postgresql://${dbUser}:${encodedPassword}@postgres:5432/${dbName}"
$settings = [ordered]@{
  "DOCKOS_ENV" = "development"
  "OPEX_ALLOW_LEGACY_HEADERS" = "true"
  "VITE_LOCAL_PILOT_MODE" = "true"
  "OPEX_ATTESTATION_MODE" = "development"
  "VITE_OIDC_CLIENT_ID" = ""
  "VITE_OIDC_AUTHORIZE_URL" = ""
  "VITE_OIDC_TOKEN_URL" = ""
  "VITE_OIDC_REDIRECT_URI" = "http://localhost:8080/auth/callback"
  "DOCKOS_NOTIFICATION_AUTOMATION" = "false"
}
foreach ($entry in $settings.GetEnumerator()) {
  $content = Set-DotEnvValue $content $entry.Key $entry.Value
}
Set-Content -Path $EnvFile -Value $content -Encoding UTF8

if ($PrepareOnly) {
  Write-Host "Yerel pilot .env ayarlari hazirlandi." -ForegroundColor Green
  return
}

Push-Location $ProjectRoot
try {
  Write-Host "OPEX Workforce yerel pilot kuruluyor..." -ForegroundColor Cyan
  docker compose config --quiet
  docker compose stop notification-worker 2>$null
  docker compose up -d --build postgres backend backup frontend
  docker compose ps
} finally {
  Pop-Location
}

Write-Host ""
Write-Host "Yerel pilot hazir: http://localhost:8080/workforce" -ForegroundColor Green
Write-Host "Picker ekranı: http://localhost:8080/workforce/app" -ForegroundColor Green
Write-Host "UYARI: SSO, App Attest/Play Integrity, APNs/FCM ve WORM bu modda devre disidir." -ForegroundColor Yellow
Write-Host "Bu modu internete acmayin ve gercek bordro/mahkeme delili olarak kullanmayin." -ForegroundColor Yellow
