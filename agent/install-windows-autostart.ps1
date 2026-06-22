# Installs the sagemcom-presence collector as a Windows scheduled task that runs at
# boot, with no window, and auto-restarts if it ever crashes. No login required.
#
# Run this ONCE, as Administrator, on the always-on PC:
#     powershell -ExecutionPolicy Bypass -File install-windows-autostart.ps1
#
# Re-run it to update the task. Use -Uninstall to remove it.

param([switch]$Uninstall)

$ErrorActionPreference = "Stop"
$TaskName = "SagemcomPresenceCollector"
$dir = $PSScriptRoot   # the agent\ folder this script lives in

if ($Uninstall) {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host "Removed scheduled task '$TaskName'."
  return
}

# --- sanity checks ---
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { throw "python not found on PATH. Install Python and 'pip install -r requirements.txt' first." }
if (-not (Test-Path "$dir\collector.py")) { throw "collector.py not found next to this script." }
if (-not (Test-Path "$dir\.env"))         { throw ".env not found. Copy .env.example to .env and fill it in first." }

# --- wrapper .bat: cd into agent\, run the collector, append logs to a file ---
$bat = "@echo off`r`ncd /d `"$dir`"`r`n`"$py`" `"$dir\collector.py`" >> `"$dir\collector.log`" 2>&1`r`n"
$batPath = "$dir\run-collector.bat"
Set-Content -Path $batPath -Value $bat -Encoding ASCII
Write-Host "Wrote $batPath (python: $py)"

# --- register the scheduled task ---
$action  = New-ScheduledTaskAction -Execute $batPath
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -MultipleInstances IgnoreNew `
  -DontStopOnIdleEnd
# Run as SYSTEM so it starts at boot without anyone logging in.
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
  -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "Registered scheduled task '$TaskName' (runs at startup as SYSTEM)."

Start-ScheduledTask -TaskName $TaskName
Write-Host "Started it now. Logs -> $dir\collector.log"
Write-Host "Check status:  Get-ScheduledTaskInfo -TaskName $TaskName"
