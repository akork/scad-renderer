# Release packaging

## Build application

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\build-release.ps1
```

## Build installer

Requires Inno Setup 6:

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\build-installer.ps1
```

Output:

```text
release\SCADRendererSetup-<VERSION>.exe
```

The setup wizard installs the full application into
`%LOCALAPPDATA%\Programs\SCADRenderer`. The folder can be changed on the
directory page.

If the application is already installed, the wizard offers:

- **Переустановить SCAD Renderer**;
- **Удалить SCAD Renderer**.

The Start Menu also gets a **Удалить SCAD Renderer** shortcut. The normal
uninstaller is registered in Windows Apps & Features. After removal, a
confirmation window is shown and closes automatically after 10 seconds.

## Release folder

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

## Manual install

```powershell
.\SCADRenderer.exe install
```

Fallback:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

## Remove

```powershell
.\SCADRenderer.exe uninstall
```

The installed setup also appears in Windows Apps & Features.

## Data

- slots: `%USERPROFILE%\slicer-slots`;
- state: `<install>\scad-variants\state`;
- recent renders: `<install>\scad-drop\state\recent.json`.

