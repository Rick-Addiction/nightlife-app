# Registra as tarefas do Ciclo E-3 (o usuario roda 1x, sem admin).
# watch_feed a cada 45min; follow_venues 1x/dia; ingest_ig (reconciliacao) semanal.
param([string]$Python = ".venv\Scripts\python.exe")
$root = (Resolve-Path ".").Path
function New-NlTask($name, $module, $trigger) {
  $action = New-ScheduledTaskAction -Execute $Python -Argument "-m $module" -WorkingDirectory $root
  Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger `
    -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable) -Force | Out-Null
  Write-Host "registrada: $name"
}
# watch_feed: a cada 45min o dia todo; o runner sai sozinho fora da janela 10-02h
$t = New-ScheduledTaskTrigger -Once -At (Get-Date) `
     -RepetitionInterval (New-TimeSpan -Minutes 45) -RepetitionDuration (New-TimeSpan -Days 3650)
New-NlTask "Nightlife-WatchFeed" "nightlife.watch_feed" $t
New-NlTask "Nightlife-Follow" "nightlife.follow_venues" (New-ScheduledTaskTrigger -Daily -At 14:00)
New-NlTask "Nightlife-Reconcile" "nightlife.ingest_ig" (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 06:00)
Write-Host "pronto. (o daily das 05h continua pelo register_daily_task.ps1)"
