# Changelog

All notable **user-facing** changes are documented here.

Technical details, implementation attempts and architecture decisions belong in
commit bodies, an optional `DEVLOG.md`, or ADRs — not in this file. The format
follows Keep a Changelog and the project uses semantic versioning.

## [Unreleased]

### Added

- `[dev.2]` Tray **Сервис** submenu with restart, local changelog and GitHub
  repository actions.
- `[dev.3]` The changelog action opens a rendered local preview in the browser,
  including changes that have not been pushed yet.
- `[dev.7]` Slicer integration is adapter-based: OrcaSlicer and Bambu Studio
  can use independent stable slots.
- `[dev.8]` Rendering always writes results next to the source file; fixed
  `SCAD` and `deliverables` folders are no longer used.

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
