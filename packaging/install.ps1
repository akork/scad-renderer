param(
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$source = Split-Path -Parent $MyInvocation.MyCommand.Path
$target = Join-Path $env:LOCALAPPDATA 'Programs\SCADRenderer'
$taskName = 'SCAD Render Tray'
$contextKey = 'HKCU:\Software\Classes\SystemFileAssociations\.scad\shell\SCADRender'
$protocols = @('scad-viewer', 'scad-gallery', 'scad-slot', 'scad-slicer', 'scad-embed')
$startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\SCAD Render.lnk'

function Stop-OldTray {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
    $escapedTarget = [regex]::Escape($target)
    Get-CimInstance Win32_Process -Filter "Name = 'SCADRenderer.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match $escapedTarget } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'tray-host\.ps1|scad-tray\.ps1' -and $_.CommandLine -match $escapedTarget } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 500
}

if ($Remove) {
    Stop-OldTray
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    foreach ($protocol in $protocols) {
        Remove-Item -LiteralPath ('HKCU:\Software\Classes\' + $protocol) -Recurse -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $contextKey -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $startMenu -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
    Write-Output 'SCAD Renderer removed.'
    exit 0
}

if (-not (Test-Path -LiteralPath $target)) {
    New-Item -ItemType Directory -Force -Path $target | Out-Null
}
if ($source.TrimEnd('\') -ne $target.TrimEnd('\')) {
    Stop-OldTray
    robocopy $source $target /E /COPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "Could not copy release folder (robocopy exit $LASTEXITCODE)"
    }
}
$exe = Join-Path $target 'SCADRenderer.exe'
if (-not (Test-Path -LiteralPath $exe)) {
    throw "SCADRenderer.exe not found in release folder: $exe"
}

$openscad = $null
$cmd = Get-Command 'openscad.exe' -ErrorAction SilentlyContinue
if ($cmd) { $openscad = $cmd.Source }

New-Item -Path $contextKey -Force | Out-Null
Set-Item -LiteralPath $contextKey -Value 'Отрендерить SCAD (PNG + STL)'
$commandKey = Join-Path $contextKey 'command'
New-Item -Path $commandKey -Force | Out-Null
Set-Item -LiteralPath $commandKey -Value ('"' + $exe + '" render-file "%1"')
if ($openscad) {
    New-ItemProperty -Path $contextKey -Name 'Icon' -Value ($openscad + ',0') -PropertyType String -Force | Out-Null
}

$commands = @{
    'scad-viewer' = 'viewer'
    'scad-gallery' = 'gallery'
    'scad-slot' = 'slot'
    'scad-slicer' = 'slicer'
    'scad-embed' = 'ensure'
}
foreach ($protocol in $protocols) {
    $key = 'HKCU:\Software\Classes\' + $protocol
    New-Item -Path $key -Force | Out-Null
    Set-Item -LiteralPath $key -Value ('URL:SCAD ' + $protocol)
    New-ItemProperty -Path $key -Name 'URL Protocol' -Value '' -PropertyType String -Force | Out-Null
    if ($openscad) {
        New-Item -Path (Join-Path $key 'DefaultIcon') -Force | Out-Null
        Set-Item -LiteralPath (Join-Path $key 'DefaultIcon') -Value ($openscad + ',0')
    }
    $protocolCommandKey = Join-Path $key 'shell\open\command'
    New-Item -Path $protocolCommandKey -Force | Out-Null
    Set-Item -LiteralPath $protocolCommandKey -Value ('"' + $exe + '" ' + $commands[$protocol] + ' "%1"')
}

$user = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction `
    -Execute "$env:SystemRoot\System32\wscript.exe" `
    -Argument ('"' + (Join-Path $target 'tray\tray-launch.vbs') + '"') `
    -WorkingDirectory (Join-Path $target 'tray')
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$trigger.Delay = 'PT15S'
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null

$ws = New-Object -ComObject WScript.Shell
$shortcut = $ws.CreateShortcut($startMenu)
$shortcut.TargetPath = "$env:SystemRoot\System32\wscript.exe"
$shortcut.Arguments = '"' + (Join-Path $target 'tray\tray-launch.vbs') + '"'
$shortcut.WorkingDirectory = Join-Path $target 'tray'
$shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,3"
$shortcut.Description = 'SCAD Render'
$shortcut.Save()

Start-ScheduledTask -TaskName $taskName
Write-Output "Installed: $target"
Write-Output "Context menu: $contextKey"
Write-Output "Task: $taskName"
