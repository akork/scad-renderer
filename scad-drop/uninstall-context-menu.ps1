#Requires -Version 5.1
$ErrorActionPreference = 'Stop'

$key = 'HKCU:\Software\Classes\SystemFileAssociations\.scad\shell\SCADRender'
if (Test-Path $key) {
    Remove-Item -Path $key -Recurse -Force
    Write-Host "Контекстное меню удалено: $key"
} else {
    Write-Host "Контекстное меню не было установлено."
}

try {
    Add-Type -Namespace ScadDrop -Name Shell32 -MemberDefinition @'
[DllImport("shell32.dll")]
public static extern void SHChangeNotify(int eventId, uint flags, IntPtr item1, IntPtr item2);
'@
    [ScadDrop.Shell32]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
} catch {
    Write-Warning "Не удалось обновить кэш Explorer: $($_.Exception.Message)"
}
