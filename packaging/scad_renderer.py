#!/usr/bin/env python3
"""Release launcher: one EXE with explicit modes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "scad-drop", ROOT / "scad-variants"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


def usage() -> int:
    print(
        "usage: SCADRenderer.exe "
        "render-file PATH | render-core ARGS... | gallery ARGS... | "
        "viewer URI | ensure URI | slot URI | slicer URI | serve [--port N] | "
        "install [--quiet] | uninstall [--quiet] | doctor",
        file=sys.stderr,
    )
    return 2


def doctor() -> int:
    from scadvariants.paths import app_root, resource_root
    from scadvariants.render import find_openscad

    print(f"app_root={app_root()}")
    print(f"resource_root={resource_root()}")
    try:
        print(f"openscad={find_openscad()}")
    except Exception as exc:
        print(f"openscad=missing ({exc})")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return usage()
    mode = args.pop(0).lower()
    if mode == "render-file":
        from scad_drop import main as drop_main

        return drop_main(["--render-file", *args])
    if mode == "render-core":
        from scad_variants import main as core_main

        return core_main(args)
    if mode == "gallery":
        from open_gallery import main as gallery_main

        return gallery_main(args)
    if mode == "viewer":
        from open_gallery import main as gallery_main

        return gallery_main(["--viewer", *args])
    if mode == "ensure":
        from open_gallery import main as gallery_main

        return gallery_main(["--ensure", *args])
    if mode == "slot":
        from slicer_action import main as slicer_main

        return slicer_main(["slot", *args])
    if mode == "slicer":
        from slicer_action import main as slicer_main

        return slicer_main(["open", *args])
    if mode == "serve":
        from scadvariants.gallery_server import main as server_main

        return server_main(["--serve", *args])
    if mode == "install":
        from scadvariants.release_install import install

        return install(quiet="--quiet" in args)
    if mode == "uninstall":
        from scadvariants.release_install import uninstall

        return uninstall(quiet="--quiet" in args)
    if mode == "doctor":
        return doctor()
    if mode in {"version", "--version", "-v"}:
        from scadvariants.paths import app_root

        try:
            print((app_root() / "VERSION").read_text(encoding="utf-8").strip())
        except OSError:
            print("unknown")
        return 0
    return usage()


if __name__ == "__main__":
    raise SystemExit(main())
