# Project instructions

- Version source of truth: `VERSION` at the repository root.
- Current version: `1.0.4`.
- Keep detailed change history in `CHANGELOG.md`; commit subjects stay short.
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
  run tests, commit as `vX.Y.Z: ...`. Do not tag each local micro-commit.
- Push in batches, not every version. Propose a push when there are at least
  **5 local versions** ahead of `origin/main` or **14 days** have passed since
  the last pushed version; wait for approval before pushing `main` and tags.
- Before the push, squash unpushed PATCH/minor commits into one release commit,
  tag the squashed commit `vX.Y.Z`, and push that release tag.
