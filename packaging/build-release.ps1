param(
    [switch]$Zip
)

$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$version = (Get-Content (Join-Path $project 'VERSION') -Raw).Trim()
$build = (Get-Content (Join-Path $project 'BUILD') -Raw).Trim()
$label = if ([int]$build -gt 0) { "$version-dev.$build" } else { $version }
$dist = Join-Path $project 'dist'
$work = Join-Path $project 'pybuild'
$release = Join-Path $project 'release'
$out = Join-Path $release ("SCADRenderer-$label-win64")
$python = Join-Path $env:USERPROFILE '.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $python = (Get-Command 'python.exe' -ErrorAction Stop).Source
}

if (Test-Path -LiteralPath $out) {
    Remove-Item -LiteralPath $out -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $out | Out-Null

& $python -m PyInstaller `
    --noconfirm --clean `
    --distpath $dist `
    --workpath $work `
    (Join-Path $PSScriptRoot 'SCADRenderer.spec')
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

Copy-Item -Path (Join-Path $dist 'SCADRenderer\*') -Destination $out -Recurse -Force
Copy-Item -LiteralPath (Join-Path $project 'VERSION') -Destination $out
Copy-Item -LiteralPath (Join-Path $project 'BUILD') -Destination $out
Copy-Item -LiteralPath (Join-Path $project 'README.md') -Destination $out

$tray = Join-Path $out 'tray'
$vendor = Join-Path $tray 'vendor'
New-Item -ItemType Directory -Force -Path $vendor | Out-Null
foreach ($name in @('scad-tray.ps1', 'tray-host.ps1', 'tray-launch.vbs', 'start-scad-tray.vbs')) {
    Copy-Item -LiteralPath (Join-Path $project ('scad-drop\' + $name)) -Destination $tray
}
Copy-Item -LiteralPath (Join-Path $project 'scad-variants\scadvariants\show-toast.ps1') -Destination $tray
Copy-Item -LiteralPath (Join-Path $project 'scad-drop\vendor\marked.min.js') -Destination $vendor
Copy-Item -LiteralPath (Join-Path $project 'scad-drop\vendor\marked.LICENSE.md') -Destination $vendor
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'install.ps1') -Destination $out

if ($Zip) {
    $zip = "$out.zip"
    if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
    Compress-Archive -Path (Join-Path $out '*') -DestinationPath $zip -CompressionLevel Optimal
    Write-Output "ZIP: $zip"
}
Write-Output "Release: $out"
Get-ChildItem -LiteralPath $out | Select-Object Name, Length | Format-Table -AutoSize
