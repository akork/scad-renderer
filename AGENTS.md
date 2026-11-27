# Project instructions

- Version source of truth: `VERSION` at the repository root.
- Local build counter: `BUILD` at the repository root.
- Current version: `1.2.0-dev.5` (`VERSION` 1.2.0, `BUILD` 5).
- After each completed local change, increment `BUILD`; display
  `VERSION-dev.BUILD`. Before a release, bump `VERSION`, reset `BUILD` to 0,
  then tag the release.
- Commit body: 1–5 short lines for meaningful changes; one sentence for
  trivial ones. State the test count and result
  (`Tests: 12 core + 17 scad-drop = 29 passed`); if none ran, say why.
  Do not duplicate the changelog.
- Follow `~/.dsh/AGENTS.md` for version bumps, commits, tags and pushes.
- Renderer entry point is the Explorer context menu:
  `scad_drop.py --render-file <path>`.
- There is no permanent folder watcher.
- Generated `state/`, browser profiles, renders and `tools/` are ignored by
  Git. Slots default to `%USERPROFILE%\slicer-slots`.
- Tests:

  ```powershell
  cd scad-variants
  python -m unittest discover -s tests
  python -m unittest discover -s ..\scad-drop\tests
  ```

- After a completed local change: increment `BUILD`, update README/version
  metadata and CHANGELOG, run tests, commit as `vX.Y.Z-dev.N: ...`.
- At release before push: choose the next SemVer, set `VERSION`, reset `BUILD`
  to 0, tag the release commit `vX.Y.Z`, and push `main` plus that tag.
- Push in batches, not every version. Propose a push when there are at least
  **5 local versions** ahead of `origin/main` or **14 days** have passed since
  the last pushed version; wait for approval before pushing `main` and tags.
- Before the push, squash unpushed PATCH/minor commits into one release commit,
  tag the squashed commit `vX.Y.Z`, and push that release tag.
