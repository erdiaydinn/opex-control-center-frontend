$ErrorActionPreference = "Stop"
$installer = Join-Path $PSScriptRoot "INSTALL_OPEX_WORKFORCE_LOCAL_PILOT_V13_1.ps1"
if (!(Test-Path $installer)) { throw "Yerel pilot kurucusu bulunamadi: $installer" }
& $installer
