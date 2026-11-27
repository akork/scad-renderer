# Changelog

All notable changes to this project are documented here.

The format follows Keep a Changelog, and the project uses semantic versioning.
Git commit subjects are short labels; this file is the detailed history.

## [1.0.4] - 2026-11-27

### Added

- Полное описание проекта на русском языке в корневом `README.md`.
- Подробные описания компонентов `scad-variants` и `scad-drop`.
- Ссылки на changelog и документацию компонентов.

### Changed

- Документация приведена в соответствие с текущим поведением: рендер из
  контекстного меню, без постоянного watcher.
- README теперь описывает установку, использование, архитектуру, тесты и
  правила Git.

### Fixed

- Удалены устаревшие разделы про автоматическое отслеживание папок,
  `Downloads`, `SCAD` и старые стартовые скрипты.

## [1.0.3] - 2026-11-27

### Added

- Root `CHANGELOG.md` as the durable, human-readable project history.
- Global and project rules requiring a changelog update with every version.
- README link to the detailed changelog.

### Changed

- Commit subjects remain short; implementation details, reasons and test
  results belong in this file.

## [1.0.2] - 2026-11-27

### Changed

- Cloud pushes are batched by version count or age instead of pushed after
  every change.
- Unpushed PATCH/minor commits are squashed into one release commit before an
  approved push.
- Git tags are created only for release commits; local micro-commits keep their
  version in `VERSION` and in the commit subject.

## [1.0.1] - 2026-11-27

### Changed

- Added a global Git policy for semantic versions and batched cloud backups.
- Push proposals now occur after five local versions or fourteen days.
- Added project-level agent instructions with test and release commands.

## [1.0.0] - 2026-11-27

### Added

- One-shot OpenSCAD variant renderer with switch detection, manifold renderer
  discovery, PNG previews and STL export.
- Incremental HTML gallery with variant cards, contact sheet, copy-path
  controls, slot controls and embedded source-code view with highlighting.
- Local gallery server on port 8765, 3D viewer and in-tab 3D modal.
- Explorer context-menu entry point for rendering one `.scad` file in place,
  anywhere on the filesystem.
- Windows tray application with active render progress, recent renders,
  folder shortcut, Edge preview and server status.
- Dedicated Edge preview profile that reuses an existing render tab and brings
  its window to the foreground.
- OrcaSlicer focus/launch helper and slot integration.
- Installation scripts for the context menu, protocols, notifications and tray
  autostart.

### Removed

- Permanent folder watcher and folder-specific auto-open behavior.
- Copying sources into a fixed `SCAD` folder.
