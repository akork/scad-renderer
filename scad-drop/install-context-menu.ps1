#Requires -Version 5.1
$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$renderCmd = Join-Path $here 'render-scad.cmd'
$dropScript = Join-Path $here 'scad_drop.py'
$python = Join-Path $env:USERPROFILE '.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
$pythonw = Join-Path (Split-Path -Parent $python) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $renderCmd)) {
    throw "Не найден render-scad.cmd: $renderCmd"
}

$openscad = $null
$command = Get-Command 'openscad.exe' -ErrorAction SilentlyContinue
if ($command) {
    $openscad = $command.Source
} elseif (Test-Path 'C:\Users\ak\scoop\shims\openscad.exe') {
    $openscad = 'C:\Users\ak\scoop\shims\openscad.exe'
}

$key = 'HKCU:\Software\Classes\SystemFileAssociations\.scad\shell\SCADRender'
New-Item -Path $key -Force | Out-Null
Set-Item -Path $key -Value 'Отрендерить SCAD (PNG + STL)'
if ($openscad) {
    New-ItemProperty -Path $key -Name 'Icon' -Value ($openscad + ',0') `
        -PropertyType String -Force | Out-Null
}

$commandKey = Join-Path $key 'command'
New-Item -Path $commandKey -Force | Out-Null
if ((Test-Path -LiteralPath $pythonw) -and (Test-Path -LiteralPath $dropScript)) {
    # pythonw.exe has no console window; this is the normal context-menu path.
    $commandLine = '"' + $pythonw + '" -u "' + $dropScript + '" --render-file "%1"'
} elseif ((Test-Path -LiteralPath $python) -and (Test-Path -LiteralPath $dropScript)) {
    $commandLine = '"' + $python + '" -u "' + $dropScript + '" --render-file "%1"'
} else {
    $commandLine = '"' + $renderCmd + '" "%1"'
}
Set-Item -Path $commandKey -Value $commandLine

# Ask Explorer to re-read associations so the new item appears without a
# full sign-out.  Existing context menus may need a new Explorer window.
try {
    Add-Type -Namespace ScadDrop -Name Shell32 -MemberDefinition @'
[DllImport("shell32.dll")]
public static extern void SHChangeNotify(int eventId, uint flags, IntPtr item1, IntPtr item2);
'@
    [ScadDrop.Shell32]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
} catch {
    Write-Warning "Не удалось обновить кэш Explorer: $($_.Exception.Message)"
}

Write-Host "Контекстное меню установлено:"
Write-Host "  $key"
Write-Host "  команда: $commandLine"
Write-Host ""
Write-Host "Правый клик по .scad -> 'Отрендерить SCAD (PNG + STL)'."
Write-Host "В Windows 11 пункт может быть в 'Показать дополнительные параметры'."
