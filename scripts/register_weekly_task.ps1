# Registers a weekly Windows Task Scheduler job that runs the pipeline for
# one council. Run this once (as the user, not elevated) per council you
# want on a schedule:
#
#   powershell -File scripts\register_weekly_task.ps1 -Council bury
#   powershell -File scripts\register_weekly_task.ps1 -Council stockport -DayOfWeek Tuesday -Time 07:00
#
# Re-running with the same -Council overwrites the existing task (so you can
# safely re-run this after moving the project folder, etc).

param(
    [Parameter(Mandatory = $true)][string]$Council,
    [string]$DayOfWeek = "Monday",
    [string]$Time = "06:00"
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$TaskName = "PropertyDealFinder_$Council"

if (-not (Test-Path $PythonExe)) {
    throw "Could not find venv python at $PythonExe - run 'python -m venv .venv' and install requirements.txt first."
}

$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "-m app.pipeline.run_weekly --council $Council" `
    -WorkingDirectory $ProjectRoot

$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DayOfWeek -At $Time

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Weekly PropertyAIgent scrape/extraction/enrichment run for $Council" `
    -Force

Write-Host "Registered scheduled task '$TaskName': every $DayOfWeek at $Time."
Write-Host "View/run it via: Get-ScheduledTask -TaskName $TaskName | Start-ScheduledTask"
