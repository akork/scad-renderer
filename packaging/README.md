# Release packaging

## Build

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\build-release.ps1
```

Output:

```text
release\SCADRenderer-<VERSION>-win64\
  SCADRenderer.exe
  _internal\
  tray\
    scad-tray.ps1
    tray-host.ps1
    tray-launch.vbs
    start-scad-tray.vbs
    show-toast.ps1
    vendor\marked.min.js
  install.ps1
  VERSION
  BUILD
  README.md
```

`SCADRenderer.exe` contains Python, Pillow, the renderer, gallery server,
slots and the 3D assets. Python is not required on the target machine.

OpenSCAD and Edge remain external.

## Install

Primary installer:

```powershell
.\SCADRenderer.exe install
```

It copies the release to `%LOCALAPPDATA%\Programs\SCADRenderer` and registers
the context menu, protocols, tray autostart and Start Menu shortcut.

Fallback for manual setup:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

## Remove

```powershell
.\SCADRenderer.exe uninstall
```

or:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Remove
```
