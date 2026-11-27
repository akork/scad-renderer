param(
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$taskName = 'SCAD Render Tray'
$hostPath = Join-Path $PSScriptRoot 'tray-host.ps1'
$launcher = Join-Path $PSScriptRoot 'tray-launch.vbs'

if ($Remove) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "Removed scheduled task: $taskName"
    exit 0
}

if (-not (Test-Path -LiteralPath $hostPath)) {
    throw "Not found: $hostPath"
}
if (-not (Test-Path -LiteralPath $launcher)) {
    throw "Not found: $launcher"
}

$user = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction `
    -Execute "$env:SystemRoot\System32\wscript.exe" `
    -Argument ('"' + $launcher + '"') `
    -WorkingDirectory (Split-Path -Parent $launcher)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$trigger.Delay = 'PT15S'
$principal = New-ScheduledTaskPrincipal `
    -UserId $user `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description 'SCAD Render tray icon: autostart at logon' `
    -Force | Out-Null

Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 3

$info = Get-ScheduledTaskInfo -TaskName $taskName
[pscustomobject]@{
    TaskName       = $taskName
    State          = (Get-ScheduledTask -TaskName $taskName).State
    LastRunTime    = $info.LastRunTime
    LastTaskResult = $info.LastTaskResult
    NextRunTime    = $info.NextRunTime
} | Format-List
