param(
  [switch]$Online
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $ProjectRoot ".env"
$script:Failed = 0
$script:Warned = 0

function Write-Result([string]$Level, [string]$Message) {
  if ($Level -eq "OK") {
    Write-Host "[OK]   $Message" -ForegroundColor Green
  } elseif ($Level -eq "WARN") {
    $script:Warned++
    Write-Host "[UYARI] $Message" -ForegroundColor Yellow
  } else {
    $script:Failed++
    Write-Host "[HATA] $Message" -ForegroundColor Red
  }
}

function Read-DotEnv([string]$Path) {
  $values = @{}
  foreach ($line in Get-Content $Path) {
    $trimmed = $line.Trim()
    if (!$trimmed -or $trimmed.StartsWith("#") -or !$trimmed.Contains("=")) { continue }
    $parts = $trimmed.Split(@("="), 2, [System.StringSplitOptions]::None)
    $values[$parts[0].Trim()] = $parts[1].Trim().Trim('"').Trim("'")
  }
  return $values
}

function Is-Missing([hashtable]$Values, [string]$Name) {
  if (!$Values.ContainsKey($Name)) { return $true }
  $value = [string]$Values[$Name]
  return !$value -or $value.Contains("CHANGE_ME") -or $value.Contains("company.example")
}

function Require-Value([hashtable]$Values, [string]$Name, [string]$Group) {
  if (Is-Missing $Values $Name) {
    Write-Result "FAIL" "$Group`: $Name eksik veya ornek degerde."
  } else {
    Write-Result "OK" "$Group`: $Name tanimli."
  }
}

function Require-Https([hashtable]$Values, [string]$Name, [string]$Group) {
  if (!(Is-Missing $Values $Name)) {
    $value = [string]$Values[$Name]
    if ($value.StartsWith("https://")) {
      Write-Result "OK" "$Group`: $Name HTTPS kullaniyor."
    } else {
      Write-Result "FAIL" "$Group`: $Name HTTPS olmali."
    }
  }
}

if (!(Test-Path $EnvFile)) {
  Write-Result "FAIL" ".env bulunamadi. Once .\INSTALL_OPEX_WORKFORCE_V13_1.ps1 calistirin."
  exit 1
}

$envValues = Read-DotEnv $EnvFile

Write-Host "`nOPEX Workforce V13.1 uretim yapilandirma kontrolu" -ForegroundColor Cyan
Write-Host "Gizli degerler ekrana yazdirilmaz.`n"

foreach ($name in @("OPEX_OIDC_ISSUER", "OPEX_OIDC_AUDIENCE", "OPEX_OIDC_JWKS_URL", "VITE_OIDC_CLIENT_ID", "VITE_OIDC_AUTHORIZE_URL", "VITE_OIDC_TOKEN_URL", "VITE_OIDC_REDIRECT_URI")) {
  Require-Value $envValues $name "OIDC"
}
foreach ($name in @("OPEX_OIDC_ISSUER", "OPEX_OIDC_JWKS_URL", "VITE_OIDC_AUTHORIZE_URL", "VITE_OIDC_TOKEN_URL", "VITE_OIDC_REDIRECT_URI")) {
  Require-Https $envValues $name "OIDC"
}
Require-Value $envValues "OPEX_PII_KEY" "PII"

if ($envValues["OPEX_ATTESTATION_MODE"] -ne "production") {
  Write-Result "FAIL" "Cihaz dogrulama production modunda degil."
} else {
  Write-Result "OK" "Cihaz dogrulama production modunda."
}
Require-Value $envValues "APPLE_APP_ATTEST_VERIFY_URL" "Apple App Attest"
Require-Value $envValues "GOOGLE_PLAY_INTEGRITY_VERIFY_URL" "Google Play Integrity"
Require-Value $envValues "OPEX_ATTESTATION_GATEWAY_TOKEN" "Attestation gateway"
Require-Https $envValues "APPLE_APP_ATTEST_VERIFY_URL" "Apple App Attest"
Require-Https $envValues "GOOGLE_PLAY_INTEGRITY_VERIFY_URL" "Google Play Integrity"

foreach ($name in @("APNS_TEAM_ID", "APNS_KEY_ID", "APNS_BUNDLE_ID")) {
  Require-Value $envValues $name "APNs"
}
if (!(Is-Missing $envValues "APNS_PRIVATE_KEY_HOST_PATH")) {
  $apnsPath = Join-Path $ProjectRoot $envValues["APNS_PRIVATE_KEY_HOST_PATH"]
  if (Test-Path $apnsPath) { Write-Result "OK" "APNs .p8 dosyasi bulundu." } else { Write-Result "FAIL" "APNs .p8 dosyasi bulunamadi: $apnsPath" }
}

Require-Value $envValues "FCM_PROJECT_ID" "FCM"
if (!(Is-Missing $envValues "GOOGLE_APPLICATION_CREDENTIALS_HOST_PATH")) {
  $googlePath = Join-Path $ProjectRoot $envValues["GOOGLE_APPLICATION_CREDENTIALS_HOST_PATH"]
  if (Test-Path $googlePath) {
    try {
      $googleJson = Get-Content $googlePath -Raw | ConvertFrom-Json
      if ($googleJson.type -eq "service_account" -and $googleJson.project_id) {
        Write-Result "OK" "FCM service-account JSON gecerli gorunuyor."
      } else {
        Write-Result "FAIL" "FCM JSON service_account turunde degil veya project_id eksik."
      }
    } catch {
      Write-Result "FAIL" "FCM JSON okunamadi."
    }
  } else {
    Write-Result "FAIL" "FCM service-account dosyasi bulunamadi: $googlePath"
  }
}

Require-Value $envValues "WORKFORCE_WORM_BUCKET" "WORM"
Require-Value $envValues "AWS_DEFAULT_REGION" "WORM"
if ((Is-Missing $envValues "AWS_ACCESS_KEY_ID") -or (Is-Missing $envValues "AWS_SECRET_ACCESS_KEY")) {
  Write-Result "WARN" "Statik AWS anahtari yok. Host/container IAM role kullaniyorsaniz bu dogrudur; yerel Docker'da degilseniz anahtarlari tanimlayin."
} else {
  Write-Result "OK" "Yerel WORM erisim bilgileri tanimli."
}

if ($Online) {
  # Sadece GET ile okunmasi gereken standart OIDC belgeleri sorgulanir. Token,
  # authorize ve attestation endpoint'leri GET kabul etmek zorunda olmadigi icin
  # burada yanlis negatif uretilmez; bunlar gercek entegrasyon testiyle dogrulanir.
  foreach ($name in @("OPEX_OIDC_ISSUER", "OPEX_OIDC_JWKS_URL")) {
    if (!(Is-Missing $envValues $name)) {
      $url = $envValues[$name]
      if ($name -eq "OPEX_OIDC_ISSUER") { $url = $url.TrimEnd("/") + "/.well-known/openid-configuration" }
      try {
        $response = Invoke-WebRequest -Uri $url -Method Get -UseBasicParsing -TimeoutSec 15
        Write-Result "OK" "$name erisilebilir (HTTP $($response.StatusCode))."
      } catch {
        Write-Result "FAIL" "$name erisilemiyor: $($_.Exception.Message)"
      }
    }
  }
}

Write-Host ""
if ($script:Failed -gt 0) {
  Write-Host "$script:Failed hata, $script:Warned uyari bulundu. Uretime gecmeyin." -ForegroundColor Red
  exit 1
}
Write-Host "Temel kontrol basarili; $script:Warned uyari var. Native cihaz ve gercek push testi yine zorunludur." -ForegroundColor Green
exit 0
