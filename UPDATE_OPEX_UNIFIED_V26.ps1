param(
  [string]$ProjectName = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Assert-LastExitCode([string]$Step) {
  if ($LASTEXITCODE -ne 0) {
    throw "$Step basarisiz oldu (exit code: $LASTEXITCODE)."
  }
}

function Wait-DockerEngine {
  docker info *> $null
  if ($LASTEXITCODE -eq 0) { return }

  $dockerDesktop = Join-Path $Env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
  if (!(Test-Path $dockerDesktop)) {
    throw "Docker Desktop bulunamadi. Once Docker Desktop'i kurun."
  }

  Write-Host "Docker Desktop baslatiliyor..." -ForegroundColor Cyan
  Start-Process $dockerDesktop

  for ($attempt = 1; $attempt -le 60; $attempt++) {
    Start-Sleep -Seconds 2
    docker info *> $null
    if ($LASTEXITCODE -eq 0) { return }
  }

  throw "Docker Engine hazir olmadi. Docker Desktop ekraninda Engine running durumunu kontrol edin."
}

function Get-ExistingOpexCompose {
  $containerIds = @(
    docker ps -a --filter "publish=8080" --filter "label=com.docker.compose.service=frontend" --format "{{.ID}}"
  ) | Where-Object { $_ -and $_.Trim() }
  if ($containerIds.Count -eq 0) {
    $containerIds = @(
      docker ps -a --filter "label=com.docker.compose.service=frontend" --format "{{.ID}}"
    ) | Where-Object { $_ -and $_.Trim() }
  }
  if ($LASTEXITCODE -ne 0 -or $containerIds.Count -eq 0) { return $null }

  foreach ($containerId in $containerIds) {
    # Windows PowerShell 5 removes the nested quotes from Docker Go templates.
    # Reading the inspect JSON avoids the "function com not defined" parsing error.
    $inspectJson = @(& docker inspect $containerId 2>$null)
    if ($LASTEXITCODE -ne 0 -or $inspectJson.Count -eq 0) { continue }

    try {
      $inspect = (($inspectJson -join [Environment]::NewLine) | ConvertFrom-Json)[0]
      $labels = $inspect.Config.Labels
      $workingDir = ([string]$labels.'com.docker.compose.project.working_dir').Trim()
      $composeProject = ([string]$labels.'com.docker.compose.project').Trim()
    } catch {
      Write-Warning "Docker container bilgisi okunamadi; sonraki OPEX frontend container'i deneniyor: $containerId"
      continue
    }

    if ($composeProject) {
      $verifiedWorkingDir = ""
      if ($workingDir -and (Test-Path (Join-Path $workingDir "docker-compose.yml"))) {
        $verifiedWorkingDir = $workingDir
      }

      return [PSCustomObject]@{
        ProjectName = $composeProject
        WorkingDir = $verifiedWorkingDir
      }
    }
  }

  return $null
}

function Invoke-OpexCompose([string[]]$Arguments, [string]$Step) {
  $dockerArgs = @("compose")
  if ($script:ResolvedProjectName) {
    $dockerArgs += @("-p", $script:ResolvedProjectName)
  }
  $dockerArgs += $Arguments

  & docker @dockerArgs
  Assert-LastExitCode $Step
}

function Read-DotEnv([string]$Path) {
  $values = @{}
  if (!(Test-Path $Path)) { return $values }

  foreach ($line in Get-Content $Path) {
    $trimmed = $line.Trim()
    if (!$trimmed -or $trimmed.StartsWith("#") -or !$trimmed.Contains("=")) { continue }

    $parts = $trimmed.Split(@("="), 2, [System.StringSplitOptions]::None)
    $name = $parts[0].Trim()
    $value = $parts[1].Trim()
    if (
      $value.Length -ge 2 -and
      (($value.StartsWith("'") -and $value.EndsWith("'")) -or
       ($value.StartsWith('"') -and $value.EndsWith('"')))
    ) {
      $value = $value.Substring(1, $value.Length - 2)
    }

    if ($name) { $values[$name] = $value }
  }

  return $values
}

function New-UrlSafeSecret([int]$ByteLength = 48) {
  $bytes = New-Object byte[] $ByteLength
  $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try {
    $generator.GetBytes($bytes)
    return ([Convert]::ToBase64String($bytes).TrimEnd([char]'=').Replace("+", "-").Replace("/", "_"))
  } finally {
    $generator.Dispose()
  }
}

function Get-ExistingContainerSettings([string]$ComposeProject) {
  $wanted = @(
    "APNS_BUNDLE_ID", "APNS_ENV", "APNS_KEY_ID", "APNS_PRIVATE_KEY_HOST_PATH", "APNS_TEAM_ID",
    "APPLE_APP_ATTEST_VERIFY_URL", "AWS_ACCESS_KEY_ID", "AWS_DEFAULT_REGION", "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN", "BACKUP_INTERVAL_SECONDS", "BACKUP_RETENTION_DAYS", "DATABASE_URL",
    "DOCKOS_BACKUP_RETENTION_DAYS", "DOCKOS_BQ_PROJECT", "DOCKOS_DC_EMAILS", "DOCKOS_ENV",
    "DOCKOS_GATEWAY_SECRET", "DOCKOS_NOTIFICATION_AUTOMATION", "DOCKOS_NOTIFICATION_INTERVAL_SECONDS",
    "DOCKOS_PO_SOURCE", "DOCKOS_SMTP_FROM", "DOCKOS_SMTP_HOST", "DOCKOS_SMTP_PASSWORD",
    "DOCKOS_SMTP_PORT", "DOCKOS_SMTP_TLS", "DOCKOS_SMTP_USER", "FCM_PROJECT_ID",
    "GOOGLE_APPLICATION_CREDENTIALS_HOST_PATH", "GOOGLE_PLAY_INTEGRITY_VERIFY_URL", "GRAFANA_ADMIN_PASSWORD",
    "OPEX_ALLOW_LEGACY_HEADERS", "OPEX_ATTESTATION_GATEWAY_TOKEN", "OPEX_ATTESTATION_MODE",
    "OPEX_BOOTSTRAP_ADMIN_PASSWORD", "OPEX_BOOTSTRAP_ADMIN_USERNAME", "OPEX_CORS_ORIGINS",
    "OPEX_LOCAL_AUTH_ENABLED", "OPEX_LOCAL_JWT_SECRET", "OPEX_OIDC_ALGORITHMS", "OPEX_OIDC_AUDIENCE",
    "OPEX_OIDC_ISSUER", "OPEX_OIDC_JWKS_URL", "OPEX_OIDC_EMPLOYEE_ID_CLAIM", "OPEX_OIDC_PERMISSIONS_CLAIM", "OPEX_OIDC_ROLES_CLAIM",
    "OPEX_OIDC_WAREHOUSE_SCOPE_CLAIM", "OPEX_PII_KEY", "OPEX_PUBLIC_BASE_URL", "POSTGRES_DB",
    "POSTGRES_PASSWORD", "POSTGRES_USER", "RECRUITMENT_SMTP_FROM", "RECRUITMENT_SMTP_HOST",
    "RECRUITMENT_SMTP_PASSWORD", "RECRUITMENT_SMTP_PORT", "RECRUITMENT_SMTP_TLS",
    "RECRUITMENT_SMTP_USER", "REDIS_PASSWORD", "REDIS_URL", "S3_ENDPOINT_URL", "SENTRY_DSN",
    "SENTRY_TRACES_SAMPLE_RATE", "VITE_API_BASE", "VITE_INVENTORY_API_REQUIRED", "VITE_LOCAL_PILOT_MODE",
    "VITE_OIDC_AUTHORIZE_URL", "VITE_OIDC_CLIENT_ID", "VITE_OIDC_REDIRECT_URI", "VITE_OIDC_SCOPE",
    "VITE_OIDC_TOKEN_URL", "WORKFORCE_PUSH_POLL_SECONDS", "WORKFORCE_WORM_BUCKET",
    "WORKFORCE_WORM_RETENTION_DAYS", "WORKFORCE_WORM_SSE", "WORM_INTERVAL_SECONDS"
  )

  $values = @{}
  $containerIds = @(
    docker ps -a --filter "label=com.docker.compose.project=$ComposeProject" --format "{{.ID}}"
  ) | Where-Object { $_ -and $_.Trim() }

  foreach ($containerId in $containerIds) {
    $inspectJson = @(& docker inspect $containerId 2>$null)
    if ($LASTEXITCODE -ne 0 -or $inspectJson.Count -eq 0) { continue }

    try {
      $inspect = (($inspectJson -join [Environment]::NewLine) | ConvertFrom-Json)[0]
      foreach ($entry in @($inspect.Config.Env)) {
        $separator = $entry.IndexOf("=")
        if ($separator -lt 1) { continue }
        $name = $entry.Substring(0, $separator)
        $value = $entry.Substring($separator + 1)
        if ($wanted -contains $name -and $value -ne "" -and !$values.ContainsKey($name)) {
          $values[$name] = $value
        }
      }
    } catch {
      Write-Warning "Container ayarlari okunamadi; sonraki container deneniyor: $containerId"
    }
  }

  return $values
}

function Write-DotEnv([string]$Path, [hashtable]$Values) {
  $preferredOrder = @(
    "DOCKOS_ENV", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "DATABASE_URL",
    "REDIS_PASSWORD", "REDIS_URL", "OPEX_LOCAL_AUTH_ENABLED", "OPEX_LOCAL_JWT_SECRET",
    "OPEX_BOOTSTRAP_ADMIN_USERNAME", "OPEX_BOOTSTRAP_ADMIN_PASSWORD", "OPEX_ALLOW_LEGACY_HEADERS",
    "OPEX_CORS_ORIGINS", "VITE_LOCAL_PILOT_MODE", "VITE_INVENTORY_API_REQUIRED", "VITE_API_BASE",
    "GRAFANA_ADMIN_PASSWORD"
  )
  $orderedNames = @($preferredOrder | Where-Object { $Values.ContainsKey($_) })
  $orderedNames += @($Values.Keys | Where-Object { $orderedNames -notcontains $_ } | Sort-Object)

  $lines = foreach ($name in $orderedNames) {
    $safeValue = ([string]$Values[$name]).Replace("'", "\'")
    "$name='$safeValue'"
  }

  $temporaryPath = "$Path.v26-new"
  [System.IO.File]::WriteAllLines(
    $temporaryPath,
    $lines,
    (New-Object System.Text.UTF8Encoding($false))
  )
  Move-Item -Force $temporaryPath $Path
}

function Repair-OpexEnv([string]$Path, [string]$ComposeProject) {
  $values = Read-DotEnv $Path
  $recovered = Get-ExistingContainerSettings $ComposeProject

  foreach ($name in $recovered.Keys) {
    if (!$values.ContainsKey($name) -or !([string]$values[$name]).Trim()) {
      $values[$name] = $recovered[$name]
    }
  }

  if (!$values.ContainsKey("POSTGRES_DB") -or !$values["POSTGRES_DB"]) { $values["POSTGRES_DB"] = "opex" }
  if (!$values.ContainsKey("POSTGRES_USER") -or !$values["POSTGRES_USER"]) { $values["POSTGRES_USER"] = "opex" }

  if (!$values.ContainsKey("DATABASE_URL") -or $values["DATABASE_URL"] -notmatch "^postgresql://.+") {
    if (!$values.ContainsKey("POSTGRES_PASSWORD") -or !$values["POSTGRES_PASSWORD"]) {
      throw "Mevcut PostgreSQL parolasi container'lardan geri alinamadi. Veri guvenligi icin ayarlar degistirilmedi."
    }
    $encodedPassword = [Uri]::EscapeDataString(([string]$values["POSTGRES_PASSWORD"]).Trim())
    $values["DATABASE_URL"] = "postgresql://$($values['POSTGRES_USER']):${encodedPassword}@postgres:5432/$($values['POSTGRES_DB'])"
  }

  if (!$values.ContainsKey("POSTGRES_PASSWORD") -or !$values["POSTGRES_PASSWORD"]) {
    throw "Mevcut PostgreSQL parolasi container'lardan geri alinamadi. Veri guvenligi icin ayarlar degistirilmedi."
  }

  if (
    !$values.ContainsKey("REDIS_PASSWORD") -or !$values["REDIS_PASSWORD"] -or
    !$values.ContainsKey("REDIS_URL") -or $values["REDIS_URL"] -notmatch "^redis://.+"
  ) {
    $redisPassword = New-UrlSafeSecret 36
    $values["REDIS_PASSWORD"] = $redisPassword
    $values["REDIS_URL"] = "redis://:${redisPassword}@redis:6379/0"
    Write-Host "Eski surumde bulunmayan Redis guvenlik anahtari olusturuldu." -ForegroundColor Green
  }

  if (
    !$values.ContainsKey("OPEX_LOCAL_JWT_SECRET") -or
    ([string]$values["OPEX_LOCAL_JWT_SECRET"]).Length -lt 48
  ) {
    $values["OPEX_LOCAL_JWT_SECRET"] = New-UrlSafeSecret 48
    Write-Host "Eski surumde bulunmayan yerel JWT anahtari olusturuldu." -ForegroundColor Green
  }

  if (!$values.ContainsKey("DOCKOS_ENV")) { $values["DOCKOS_ENV"] = "local" }
  if (!$values.ContainsKey("OPEX_LOCAL_AUTH_ENABLED")) { $values["OPEX_LOCAL_AUTH_ENABLED"] = "true" }
  if (!$values.ContainsKey("OPEX_ALLOW_LEGACY_HEADERS")) { $values["OPEX_ALLOW_LEGACY_HEADERS"] = "true" }
  if (!$values.ContainsKey("OPEX_CORS_ORIGINS")) { $values["OPEX_CORS_ORIGINS"] = "http://localhost:8080" }
  if (!$values.ContainsKey("VITE_LOCAL_PILOT_MODE")) { $values["VITE_LOCAL_PILOT_MODE"] = "true" }
  if (!$values.ContainsKey("VITE_INVENTORY_API_REQUIRED")) { $values["VITE_INVENTORY_API_REQUIRED"] = "true" }
  if (!$values.ContainsKey("VITE_API_BASE")) { $values["VITE_API_BASE"] = "/api" }

  $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  if (Test-Path $Path) {
    Copy-Item $Path "$Path.partial-before-repair-$stamp"
  }
  Write-DotEnv $Path $values
  Write-Host ".env mevcut PostgreSQL ayarlari korunarak tamamlandi." -ForegroundColor Green
}

if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker komutu bulunamadi. Docker Desktop'i kurup tekrar deneyin."
}

Wait-DockerEngine

$existing = Get-ExistingOpexCompose
$ResolvedProjectName = $ProjectName
if (!$ResolvedProjectName -and $existing) {
  $ResolvedProjectName = $existing.ProjectName
  Write-Host "Mevcut OPEX Docker projesi bulundu: $ResolvedProjectName" -ForegroundColor Green
}

if (!$ResolvedProjectName) {
  throw "Mevcut OPEX Docker projesi bulunamadi. Veri guvenligi icin yeni ve bos bir Docker projesi olusturulmadi. Once mevcut OPEX container'larini baslatin veya scripti dogru -ProjectName degeriyle calistirin."
}

$envFile = Join-Path $ProjectRoot ".env"
if (!(Test-Path $envFile) -and $existing -and $existing.WorkingDir) {
  $existingEnv = Join-Path $existing.WorkingDir ".env"
  if (Test-Path $existingEnv) {
    Copy-Item $existingEnv $envFile
    Write-Host "Mevcut OPEX ayarlari korundu." -ForegroundColor Green
  }
}

$envValues = Read-DotEnv $envFile
$requiredEnvReady = (
  $envValues.ContainsKey("POSTGRES_PASSWORD") -and $envValues["POSTGRES_PASSWORD"] -and
  $envValues.ContainsKey("DATABASE_URL") -and $envValues["DATABASE_URL"] -match "^postgresql://.+" -and
  $envValues.ContainsKey("REDIS_PASSWORD") -and $envValues["REDIS_PASSWORD"] -and
  $envValues.ContainsKey("REDIS_URL") -and $envValues["REDIS_URL"] -match "^redis://.+" -and
  $envValues.ContainsKey("OPEX_LOCAL_JWT_SECRET") -and ([string]$envValues["OPEX_LOCAL_JWT_SECRET"]).Length -ge 48
)

if (!$requiredEnvReady) {
  Write-Host "Eksik veya eski .env ayarlari mevcut container'lardan tamamlaniyor..." -ForegroundColor Cyan
  Repair-OpexEnv $envFile $ResolvedProjectName
  $envValues = Read-DotEnv $envFile
}

if ($envValues["DATABASE_URL"] -notmatch "^postgresql://.+") {
  throw "Mevcut .env icinde gecerli DATABASE_URL olusturulamadi. Veri guvenligi icin servisler degistirilmedi."
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
Copy-Item $envFile (Join-Path $ProjectRoot ".env.before-v26-$stamp")

Push-Location $ProjectRoot
try {
  Invoke-OpexCompose @("config", "--quiet") "Docker Compose yapilandirma kontrolu"

  Write-Host "OPEX Unified V26.7 image'lari onbelge kullanmadan derleniyor..." -ForegroundColor Cyan
  Invoke-OpexCompose @("build", "--no-cache", "backend", "frontend") "Frontend/backend derlemesi"

  Write-Host "Mevcut veriler korunarak servisler yenileniyor..." -ForegroundColor Cyan
  Invoke-OpexCompose @(
    "up", "-d", "--force-recreate",
    "postgres", "redis", "backend", "notification-worker", "backup", "frontend"
  ) "OPEX servis yenilemesi"

  $healthChecks = @(
    "http://localhost:8000/api/workforce/health",
    "http://localhost:8000/api/recruitment/health",
    "http://localhost:8000/api/inventory/health"
  )

  foreach ($healthUrl in $healthChecks) {
    $ready = $false
    for ($attempt = 1; $attempt -le 40; $attempt++) {
      try {
        $response = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3
        if ($response.status -in @("ok", "ready")) {
          $ready = $true
          break
        }
      } catch {
        Start-Sleep -Seconds 2
      }
    }

    if (!$ready) {
      throw "Saglik kontrolu basarisiz: $healthUrl. 'docker compose logs --tail 120 backend' ciktisini inceleyin."
    }
  }

  $frontendCheck = "grep -R -q 'Workforce Control' /usr/share/nginx/html/assets && grep -R -q 'Hiring Control' /usr/share/nginx/html/assets && grep -R -q 'Inventory' /usr/share/nginx/html/assets && grep -R -q 'Modülleri Yenile' /usr/share/nginx/html/assets && grep -R -q 'Şifre sıfırla' /usr/share/nginx/html/assets"
  $dockerArgs = @("compose")
  if ($ResolvedProjectName) { $dockerArgs += @("-p", $ResolvedProjectName) }
  $dockerArgs += @("exec", "-T", "frontend", "sh", "-c", $frontendCheck)
  & docker @dockerArgs
  Assert-LastExitCode "Frontend platform karti ve Access Control dogrulamasi"

  Invoke-OpexCompose @("ps") "Servis durum kontrolu"
} finally {
  Pop-Location
}

$networkConfig = Get-NetIPConfiguration -ErrorAction SilentlyContinue |
  Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq "Up" } |
  Sort-Object { $_.NetIPv4Interface.InterfaceMetric } |
  Select-Object -First 1
$localIp = $networkConfig.IPv4Address.IPAddress

Write-Host ""
Write-Host "OPEX Unified V26.7 hazir: http://localhost:8080" -ForegroundColor Green
Write-Host "Workforce: http://localhost:8080/workforce" -ForegroundColor Cyan
Write-Host "Hiring:   http://localhost:8080/recruitment" -ForegroundColor Cyan
Write-Host "Inventory:http://localhost:8080/inventory" -ForegroundColor Cyan
if ($localIp) {
  Write-Host "Ofis agi:  http://${localIp}:8080" -ForegroundColor Cyan
}
Write-Host "Docker volume'lari silinmedi; mevcut veriler korundu." -ForegroundColor Yellow
