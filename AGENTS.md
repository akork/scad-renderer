# Project instructions

- Version source of truth: `VERSION` at the repository root.
- Current version: `1.0.0`.
- Follow `~/.dsh/AGENTS.md` for version bumps, commits, tags and pushes.
- Renderer entry point is the Explorer context menu:
  `scad_drop.py --render-file <path>`.
- There is no permanent folder watcher.
- Generated `state/`, browser profiles, renders, `SCAD/`, `orca-slots/`,
  `tools/` and `deliverables/` are ignored by Git.
- Tests:

  ```powershell
  cd scad-variants
  python -m unittest discover -s tests
  python -m unittest discover -s ..\scad-drop\tests
  ```

- After a completed change: bump `VERSION`, update README/version metadata,
  run tests, commit as `vX.Y.Z: ...`, tag `vX.Y.Z`, push `main` and the tag.
