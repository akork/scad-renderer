# Scoop bucket

Install:

```powershell
scoop bucket add scad https://github.com/akork/scad-renderer
scoop install scad/scad-renderer
```

The package keeps application state under Scoop `persist`:

```text
~/scoop/persist/scad-renderer/
  scad-drop/state/
  scad-variants/state/
```

A normal `scoop update scad-renderer` keeps that state.

Remove the application but keep state:

```powershell
scoop uninstall scad-renderer
```

Remove the application and persisted state:

```powershell
scoop uninstall scad-renderer --purge
```

Slots remain outside the package:

```text
%USERPROFILE%\slicer-slots
```
