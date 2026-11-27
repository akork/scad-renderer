param(
    [string]$Version = ''
)

$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
if (-not $Version) {
    $semver = (Get-Content (Join-Path $project 'VERSION') -Raw).Trim()
    $build = (Get-Content (Join-Path $project 'BUILD') -Raw).Trim()
    $Version = if ([int]$build -gt 0) { "$semver-dev.$build" } else { $semver }
}

$iscc = Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'
if (-not (Test-Path -LiteralPath $iscc)) {
    $iscc = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
}
if (-not (Test-Path -LiteralPath $iscc)) {
    throw 'ISCC.exe not found. Install Inno Setup 6.'
}

$release = Join-Path $project ("release\SCADRenderer-$Version-win64")
if (-not (Test-Path -LiteralPath (Join-Path $release 'SCADRenderer.exe'))) {
    throw "Release folder not found: $release. Run build-release.ps1 first."
}

& $iscc "/DMyAppVersion=$Version" (Join-Path $PSScriptRoot 'SCADRenderer.iss')
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed with exit code $LASTEXITCODE"
}

$setup = Join-Path $project ("release\SCADRendererSetup-$Version.exe")
if (-not (Test-Path -LiteralPath $setup)) {
    throw "Setup EXE not produced: $setup"
}
Get-Item -LiteralPath $setup | Select-Object FullName, Length, LastWriteTime | Format-List
