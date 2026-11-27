$keys = @(
    'HKCU:\Software\Classes\scad-viewer',
    'HKCU:\Software\Classes\scad-gallery',
    'HKCU:\Software\Classes\scad-slot',
    'HKCU:\Software\Classes\scad-slicer',
    'HKCU:\Software\Classes\scad-embed'
)
foreach ($key in $keys) {
    if (Test-Path $key) {
        Remove-Item -Path $key -Recurse -Force
        Write-Output "Protocol removed: $key"
    }
}
