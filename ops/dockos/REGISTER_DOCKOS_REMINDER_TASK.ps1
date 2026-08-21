param([string]$TaskName = "DockOS-Reservation-Reminders")
$ErrorActionPreference = "Stop"
$runner = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "RUN_DOCKOS_REMINDERS.ps1"
if (!(Test-Path $runner)) { throw "Hatirlatma scripti bulunamadi: $runner" }
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`""
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
Write-Host "DockOS hatirlatma gorevi kaydedildi: her 15 dakikada bir." -ForegroundColor Green
