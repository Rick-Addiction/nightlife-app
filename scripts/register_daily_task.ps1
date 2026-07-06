# Registra a tarefa diaria no Windows Task Scheduler (usuario atual, sem admin).
# Uso: powershell -ExecutionPolicy Bypass -File scripts\register_daily_task.ps1 -At 05:00
param([string]$At = "05:00")

$bat = Join-Path $PSScriptRoot "daily.bat"
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$bat`""
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

Register-ScheduledTask -TaskName "NightlifeDaily" -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "Tarefa 'NightlifeDaily' registrada — diaria as $At (roda so quando logado)."
