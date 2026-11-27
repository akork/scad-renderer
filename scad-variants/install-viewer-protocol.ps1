$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$gallery = Join-Path $here 'open_gallery.py'
$slicer = Join-Path $here 'slicer_action.py'

function Resolve-Pythonw {
    $candidates = @(
        (Join-Path $env:USERPROFILE '.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\pythonw.exe')
    )
    $fromPath = Get-Command 'pythonw.exe' -ErrorAction SilentlyContinue
    if ($fromPath) { $candidates += $fromPath.Source }
    $python = Get-Command 'python.exe' -ErrorAction SilentlyContinue
    if ($python) { $candidates += (Join-Path (Split-Path -Parent $python.Source) 'pythonw.exe') }
    try {
        $launcher = Get-Command 'py.exe' -ErrorAction SilentlyContinue
        if ($launcher) {
            $pyPath = & $launcher.Source -3 -c "import sys; print(sys.executable)" 2>$null
            if ($pyPath) { $candidates += (Join-Path (Split-Path -Parent ([string]$pyPath).Trim()) 'pythonw.exe') }
        }
    } catch { }
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) { return $candidate }
    }
    return $null
}

$pythonw = Resolve-Pythonw
if (-not $pythonw) {
    throw "pythonw.exe not found. Install Python 3.10+ with Pillow, or add pythonw.exe to PATH."
}

$openscad = $null
$osc = Get-Command 'openscad.exe' -ErrorAction SilentlyContinue
if ($osc) {
    $openscad = $osc.Source
} elseif (Test-Path 'C:\Users\ak\scoop\shims\openscad.exe') {
    $openscad = 'C:\Users\ak\scoop\shims\openscad.exe'
}

if (-not (Test-Path -LiteralPath $gallery)) { throw "Not found: $gallery" }
if (-not (Test-Path -LiteralPath $slicer)) { throw "Not found: $slicer" }

$key = 'HKCU:\Software\Classes\scad-viewer'
New-Item -Path $key -Force | Out-Null
Set-Item -Path $key -Value 'URL:SCAD Viewer'
New-ItemProperty -Path $key -Name 'URL Protocol' -Value '' -PropertyType String -Force | Out-Null
if (Test-Path -LiteralPath $openscad) {
    New-Item -Path (Join-Path $key 'DefaultIcon') -Force | Out-Null
    Set-Item -Path (Join-Path $key 'DefaultIcon') -Value ($openscad + ',0')
}
$commandKey = Join-Path $key 'shell\open\command'
New-Item -Path $commandKey -Force | Out-Null
$command = '"' + $pythonw + '" "' + $gallery + '" --viewer "%1"'
Set-Item -Path $commandKey -Value $command
Write-Output "Protocol installed: scad-viewer"
Write-Output "  $command"

$galleryKey = 'HKCU:\Software\Classes\scad-gallery'
New-Item -Path $galleryKey -Force | Out-Null
Set-Item -Path $galleryKey -Value 'URL:SCAD Gallery'
New-ItemProperty -Path $galleryKey -Name 'URL Protocol' -Value '' -PropertyType String -Force | Out-Null
if (Test-Path -LiteralPath $openscad) {
    New-Item -Path (Join-Path $galleryKey 'DefaultIcon') -Force | Out-Null
    Set-Item -Path (Join-Path $galleryKey 'DefaultIcon') -Value ($openscad + ',0')
}
$galleryCommandKey = Join-Path $galleryKey 'shell\open\command'
New-Item -Path $galleryCommandKey -Force | Out-Null
$galleryCommand = '"' + $pythonw + '" "' + $gallery + '" "%1"'
Set-Item -Path $galleryCommandKey -Value $galleryCommand
Write-Output "Protocol installed: scad-gallery"
Write-Output "  $galleryCommand"

$slotKey = 'HKCU:\Software\Classes\scad-slot'
New-Item -Path $slotKey -Force | Out-Null
Set-Item -Path $slotKey -Value 'URL:SCAD Slot'
New-ItemProperty -Path $slotKey -Name 'URL Protocol' -Value '' -PropertyType String -Force | Out-Null
if (Test-Path -LiteralPath $openscad) {
    New-Item -Path (Join-Path $slotKey 'DefaultIcon') -Force | Out-Null
    Set-Item -Path (Join-Path $slotKey 'DefaultIcon') -Value ($openscad + ',0')
}
$slotCommandKey = Join-Path $slotKey 'shell\open\command'
New-Item -Path $slotCommandKey -Force | Out-Null
$slotCommand = '"' + $pythonw + '" "' + $slicer + '" slot "%1"'
Set-Item -Path $slotCommandKey -Value $slotCommand
Write-Output "Protocol installed: scad-slot"
Write-Output "  $slotCommand"

$slicerKey = 'HKCU:\Software\Classes\scad-slicer'
New-Item -Path $slicerKey -Force | Out-Null
Set-Item -Path $slicerKey -Value 'URL:SCAD Slicer'
New-ItemProperty -Path $slicerKey -Name 'URL Protocol' -Value '' -PropertyType String -Force | Out-Null
if (Test-Path -LiteralPath $openscad) {
    New-Item -Path (Join-Path $slicerKey 'DefaultIcon') -Force | Out-Null
    Set-Item -Path (Join-Path $slicerKey 'DefaultIcon') -Value ($openscad + ',0')
}
$slicerCommandKey = Join-Path $slicerKey 'shell\open\command'
New-Item -Path $slicerCommandKey -Force | Out-Null
$slicerCommand = '"' + $pythonw + '" "' + $slicer + '" open "%1"'
Set-Item -Path $slicerCommandKey -Value $slicerCommand
Write-Output "Protocol installed: scad-slicer"
Write-Output "  $slicerCommand"

$embedKey = 'HKCU:\Software\Classes\scad-embed'
New-Item -Path $embedKey -Force | Out-Null
Set-Item -Path $embedKey -Value 'URL:SCAD Embed Server'
New-ItemProperty -Path $embedKey -Name 'URL Protocol' -Value '' -PropertyType String -Force | Out-Null
if (Test-Path -LiteralPath $openscad) {
    New-Item -Path (Join-Path $embedKey 'DefaultIcon') -Force | Out-Null
    Set-Item -Path (Join-Path $embedKey 'DefaultIcon') -Value ($openscad + ',0')
}
$embedCommandKey = Join-Path $embedKey 'shell\open\command'
New-Item -Path $embedCommandKey -Force | Out-Null
$embedCommand = '"' + $pythonw + '" "' + $gallery + '" --ensure "%1"'
Set-Item -Path $embedCommandKey -Value $embedCommand
Write-Output "Protocol installed: scad-embed"
Write-Output "  $embedCommand"
