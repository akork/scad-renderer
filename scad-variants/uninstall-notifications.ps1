#Requires -Version 5.1
$ErrorActionPreference = 'Stop'

$programs = [Environment]::GetFolderPath('Programs')
$lnk = Join-Path $programs 'SCAD Render.lnk'
if (Test-Path -LiteralPath $lnk) {
    Remove-Item -LiteralPath $lnk -Force
    Write-Host "Ярлык уведомлений удалён: $lnk"
} else {
    Write-Host "Ярлык уведомлений не был установлен."
}
