#!/usr/bin/env python3
"""Release launcher: one EXE with explicit modes."""

from __future__ import annotations

import os
import subprocess
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
        "tray | install [--quiet] | uninstall [--quiet] | unregister [--quiet] | "
        "doctor",
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


def _pop_option(args: list[str], name: str) -> str | None:
    if name not in args:
        return None
    index = args.index(name)
    if index + 1 >= len(args):
        return None
    value = args[index + 1]
    del args[index : index + 2]
    return value


def launch_tray() -> int:
    tray_dir = (
        Path(sys.executable).resolve().parent / "tray"
        if getattr(sys, "frozen", False)
        else ROOT / "scad-drop"
    )
    vbs = tray_dir / "tray-launch.vbs"
    if not vbs.is_file():
        return 1
    subprocess.Popen(
        [str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "wscript.exe"), str(vbs)],
        cwd=str(tray_dir),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return usage()
    mode = args.pop(0).lower()
    target = _pop_option(args, "--target")
    quiet = "--quiet" in args
    if quiet:
        args.remove("--quiet")
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

        return install(quiet=quiet, target=target)
    if mode == "uninstall":
        from scadvariants.release_install import uninstall

        return uninstall(quiet=quiet, target=target)
    if mode == "unregister":
        from scadvariants.release_install import unregister

        return unregister(quiet=quiet, target=target)
    if mode == "tray":
        return launch_tray()
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
