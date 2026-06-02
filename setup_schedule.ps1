# Bitsol Marketing — LinkedIn Auto-Poster Scheduler
# Creates 5 Windows Task Scheduler jobs, one per post per day
# Run once as Administrator: powershell -ExecutionPolicy Bypass -File setup_schedule.ps1

$PythonExe = (Get-Command python).Source
$Script    = "d:\Hermas\post_now.py"
$TaskBase  = "BitsolMarketing_LinkedIn"

# Optimal LinkedIn posting times (local time)
$Schedule = @(
    @{ Hour = 8;  Minute = 0;  Pillar = "tip" },
    @{ Hour = 10; Minute = 30; Pillar = "insight" },
    @{ Hour = 12; Minute = 30; Pillar = "case_study" },
    @{ Hour = 15; Minute = 0;  Pillar = "strategy" },
    @{ Hour = 17; Minute = 30; Pillar = "engagement" }
)

foreach ($slot in $Schedule) {
    $TaskName = "${TaskBase}_$($slot.Pillar)"
    $Time     = "{0:D2}:{1:D2}" -f $slot.Hour, $slot.Minute

    # Remove existing task if present
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    $Action  = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$Script`" --pillar $($slot.Pillar)"
    $Trigger = New-ScheduledTaskTrigger -Daily -At $Time
    $Settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -StartWhenAvailable

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -RunLevel Highest `
        -Force | Out-Null

    Write-Host "Scheduled: $TaskName at $Time"
}

Write-Host "`nAll 5 tasks registered. Run 'Get-ScheduledTask -TaskPath \' to verify."
