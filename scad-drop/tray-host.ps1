param(
    [string]$Downloads = '',
    [string]$StateDir = '',
    [string]$InstanceName = 'ScadDropTray'
)

$ErrorActionPreference = 'Stop'
if (-not $Downloads) { $Downloads = Join-Path $env:USERPROFILE 'Downloads' }
if (-not $StateDir) { $StateDir = Join-Path $PSScriptRoot 'state' }
Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;
namespace ScadTrayHost {
    public static class Native {
        [DllImport("kernel32.dll")]
        public static extern bool FreeConsole();
    }
}
'@
[ScadTrayHost.Native]::FreeConsole() | Out-Null

$trayScript = Join-Path $PSScriptRoot 'scad-tray.ps1'
$logPath = Join-Path $StateDir 'tray-host.log'
$powershell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

function Write-HostLog([string]$Message) {
    try {
        Add-Content -LiteralPath $logPath -Encoding UTF8 `
            -Value ("{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message)
    } catch { }
}

if (-not (Test-Path -LiteralPath $trayScript)) {
    Write-HostLog "tray script missing: $trayScript"
    exit 1
}

while ($true) {
    $argLine = '-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File "' +
        $trayScript + '"' +
        ' -Downloads "' + $Downloads + '"' +
        ' -StateDir "' + $StateDir + '"' +
        ' -InstanceName "' + $InstanceName + '"'

    Write-HostLog 'starting tray process'
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $powershell
    $psi.Arguments = $argLine
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $psi.WorkingDirectory = $PSScriptRoot
    $proc = [System.Diagnostics.Process]::Start($psi)
    $proc.WaitForExit()

    if ($proc.ExitCode -ne 42) {
        Write-HostLog "tray exited with code $($proc.ExitCode)"
        break
    }

    Write-HostLog 'tray requested restart; restarting in 2 seconds'
    Start-Sleep -Seconds 2
}
