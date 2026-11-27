# SCAD Renderer

Source repository for the local OpenSCAD variant renderer, Explorer context-menu
integration, tray control panel, gallery server and 3D preview.

The project is intentionally source-only: generated renders, browser profiles,
OpenSCAD binaries and machine-specific state are ignored by Git.

## Repository layout

```text
.
├─ scad-variants/       # renderer, gallery generator, local HTTP server, 3D viewer
├─ scad-drop/           # Explorer context menu, tray, recent renders
├─ README.md
└─ .gitignore
```

Clone this repository into a workspace that contains the two sibling folders
above. The installers derive their own location from `$PSScriptRoot`; the main
remaining machine-specific item is the Python interpreter path.

## Requirements

- Windows 11
- Python 3.10+ with Pillow
- OpenSCAD (current setup uses the portable Manifold build, with the installed
  OpenSCAD as fallback)
- Microsoft Edge

The existing machine uses the DeepSeek Harness Python at:

```text
%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\pythonw.exe
```

The protocol installer uses that path when present and falls back to
`pythonw.exe` from `PATH`.

## Install on a machine

1. Clone/copy the repository so that `scad-variants/` and `scad-drop/` are
   siblings.
2. Install the Explorer context menu:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scad-drop\install-context-menu.ps1
   ```

3. Install the local protocol handlers (`scad-gallery`, `scad-slot`,
   `scad-slicer`, `scad-embed`):

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scad-variants\install-viewer-protocol.ps1
   ```

4. Install tray autostart:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scad-drop\install-tray-autostart.ps1
   ```

5. Optionally recreate the Start Menu shortcut / toast AUMID:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scad-variants\install-notifications.ps1
   ```

## Usage

Render any `.scad` file from Explorer:

```text
Right click → Отрендерить SCAD (PNG + STL)
```

The renderer writes `<name>_renders/` next to the source file and opens the
gallery. There is no permanent folder watcher.

The tray icon **SCAD Render** shows:

- active render progress;
- recent renders (name + date/time);
- preview in the dedicated Edge profile on the name, folder icon for the render
  directory;
- local gallery server status.

## Architecture

- `scad_variants.py` — one-shot variant renderer and gallery builder.
- `scadvariants/gallery.py` — HTML gallery, split code view, 3D UI.
- `scadvariants/gallery_server.py` — local HTTP server (default port `8765`).
- `viewer/viewer.html` — Three.js 3D viewer.
- `scad-drop/scad_drop.py --render-file` — Explorer context-menu entry point.
- `scad-drop/scad-tray.ps1` — WinForms tray UI.
- `scad-drop/tray-host.ps1` + `tray-launch.vbs` — hidden host/relaunch loop.

Runtime folders such as `scad-variants/state/` and `scad-drop/state/` are
machine-local and ignored.

## Tests

```powershell
cd scad-variants
python -m unittest discover -s tests
```

## Git

The repository is ready for GitHub. It is currently stored at:

```text
https://github.com/akork/scad-renderer
```

The repository is **private**. Clone it anywhere and keep `scad-variants/` and
`scad-drop/` as sibling folders:

```powershell
git clone https://github.com/akork/scad-renderer.git
```

After later edits:

```powershell
git add .
git commit -m "Describe the change"
git push
```
