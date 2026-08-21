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
  throw "Docker Desktop bulunamadi. Kurup actiktan sonra bu dosyayi .\INSTALL_OPEX_WORKFORCE_V13_1.ps1 seklinde calistirin."
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
  Write-Host ".env guvenli yerel anahtarlarla olusturuldu." -ForegroundColor Green
}

# Eski paketlerden kalan .env dosyalarinda DATABASE_URL bulunmayabilir veya
# parola URL icinde encode edilmemis olabilir. Her kurulumda guvenli sekilde yenile.
$envText = Get-Content $EnvFile -Raw
$dbUserLine = [Regex]::Match($envText, "(?m)^POSTGRES_USER=(.*)$")
$dbPasswordLine = [Regex]::Match($envText, "(?m)^POSTGRES_PASSWORD=(.*)$")
$dbNameLine = [Regex]::Match($envText, "(?m)^POSTGRES_DB=(.*)$")
if (!$dbUserLine.Success -or !$dbPasswordLine.Success -or !$dbNameLine.Success) {
  throw "PostgreSQL .env ayarlari eksik. POSTGRES_USER, POSTGRES_PASSWORD ve POSTGRES_DB zorunludur."
}
$encodedPassword = [Uri]::EscapeDataString($dbPasswordLine.Groups[1].Value.Trim())
$envText = Set-DotEnvValue $envText "DATABASE_URL" "postgresql://$($dbUserLine.Groups[1].Value.Trim()):${encodedPassword}@postgres:5432/$($dbNameLine.Groups[1].Value.Trim())"
Set-Content -Path $EnvFile -Value $envText -Encoding UTF8

$required = @("OPEX_OIDC_ISSUER", "OPEX_OIDC_AUDIENCE", "OPEX_OIDC_JWKS_URL")
$envText = Get-Content $EnvFile -Raw
$missing = @($required | Where-Object { $envText -match "(?m)^$($_)=https://.*example" })
if ($missing.Count -gt 0) {
  Write-Warning "SSO adresleri kurum degerleriyle doldurulmadi: $($missing -join ', '). Sistem kurulacak; production JWT girisi bu degerler tamamlanana kadar fail-closed kalir."
}

Push-Location $ProjectRoot
try {
  Write-Host "PostgreSQL, API, bildirim worker, yedek ve frontend kuruluyor..." -ForegroundColor Cyan
  docker compose config --quiet
  docker compose up -d --build postgres backend notification-worker backup frontend
  docker compose ps
} finally {
  Pop-Location
}

Write-Host "OPEX Workforce V13.1 kuruldu: http://localhost:8080/workforce" -ForegroundColor Green
Write-Host "Komut: .\INSTALL_OPEX_WORKFORCE_V13_1.ps1" -ForegroundColor Yellow
Write-Host "Uretim ayarlari: docs\URETIM_YAPILANDIRMA_REHBERI_V13_1.md" -ForegroundColor Cyan
Write-Host "Kontrol: .\CHECK_OPEX_CONFIG_V13_1.ps1 -Online" -ForegroundColor Cyan
Write-Host "WORM: docker compose --profile worm up -d worm-archiver" -ForegroundColor Cyan
Write-Host "Izleme: docker compose --profile observability up -d prometheus grafana" -ForegroundColor Cyan
