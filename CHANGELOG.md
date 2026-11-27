# Changelog

All notable **user-facing** changes are documented here.

Technical details, implementation attempts and architecture decisions belong in
commit bodies, an optional `DEVLOG.md`, or ADRs — not in this file. The format
follows Keep a Changelog and the project uses semantic versioning.

## [1.3.0] - 2026-11-27

### Added

- A standard Windows setup wizard, `SCADRendererSetup.exe`, with:
  - installation into a selected folder;
  - reinstall or removal when the application is already installed;
  - optional cleanup of settings, logs and the preview browser profile;
  - a timed removal confirmation.
- A single `SCADRenderer.exe` that bundles Python, Pillow, the renderer,
  gallery server, slots and 3D viewer assets.
- Configurable slot storage from the tray.

### Changed

- The default slot folder is now `%USERPROFILE%\slicer-slots` instead of the
  project-local `orca-slots` folder.

## [1.2.0] - 2026-11-27

### Added

- Tray **Сервис** submenu with restart, local changelog and GitHub actions.
- Local changelog preview in the browser, including unpushed changes.
- Bambu Studio support alongside OrcaSlicer, with independent slot storage.
- Recent-render list follows context-menu renders anywhere on disk.

### Changed

- Slots are stored in the project-local `orca-slots` folder; a frozen EXE uses
  the folder next to the executable.
- OpenSCAD discovery is portable: environment, app-relative, `PATH`, standard
  install folders, Scoop and Chocolatey.

### Removed

- The “open in OpenSCAD” action and the bundled portable OpenSCAD copy.
- The fixed `SCAD` and `deliverables` folders.

## [1.1.2] - 2026-11-27

### Fixed

- The left-click tray menu no longer creates an extra button in the Windows
  taskbar.

## [1.1.1] - 2026-11-27

### Fixed

- Setup works on another computer without the original DeepSeek Harness Python
  path.

## [1.1.0] - 2026-11-27

### Added

- The tray shows the local development build label.
- Hovering the folder icon in a recent render shows the full render folder path.

### Changed

- Recent-render rows keep the render name on the left and the date/time on one
  line in the right-hand column; the em dash separator was removed.

## [1.0.4] - 2026-11-27

### Added

- Complete Russian project documentation in the root `README.md`.
- Detailed documentation for the `scad-variants` and `scad-drop` components.

### Changed

- Documentation now reflects context-menu rendering without a permanent folder
  watcher.

### Removed

- Stale documentation for folder watching, `Downloads`, `SCAD` and old startup
  scripts.

## [1.0.3] - 2026-11-27

### Added

- `CHANGELOG.md` as the durable, user-readable release history.
- A README link to the changelog.

## [1.0.2] - 2026-11-27

### Changed

- No user-facing changes; release and versioning process only.

## [1.0.1] - 2026-11-27

### Changed

- No user-facing changes; release and versioning process only.

## [1.0.0] - 2026-11-27

### Added

- One-shot OpenSCAD variant renderer with switch detection, PNG previews and
  STL export.
- HTML gallery with variant cards, contact sheet, copy-path controls, slot
  controls and embedded source-code view.
- Local gallery server, 3D viewer and in-gallery 3D modal.
- Explorer context-menu entry point for rendering one `.scad` file in place,
  anywhere on the filesystem.
- Windows tray application with active render progress, recent renders, folder
  shortcut, Edge preview and server status.
- Dedicated Edge preview profile that reuses an existing render tab and brings
  its window to the foreground.
- OrcaSlicer focus/launch helper and slot integration.
- Installation scripts for the context menu, protocols, notifications and tray
  autostart.

### Removed

- Permanent folder watching and folder-specific auto-open behavior.
- Copying sources into a fixed `SCAD` folder.
