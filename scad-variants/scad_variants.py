from __future__ import annotations

import argparse
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from scadvariants.render import (
    RenderSettings,
    find_openscad,
    openscad_version,
)
from scadvariants.watch import APP_VERSION_DISPLAY, WatchConfig, Watcher, _now_iso

DEFAULT_INPUT_DIR = "SCAD"
PROJECT_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = PROJECT_DIR.parent


def _default_root() -> Path:
    return WORKSPACE_DIR / DEFAULT_INPUT_DIR


def _default_state() -> Path:
    return PROJECT_DIR / "state"


def _parse_size(value: str) -> tuple[int, int]:
    text = value.lower().replace("х", "x").replace(",", "x")
    try:
        w, h = text.split("x", 1)
        width, height = int(w), int(h)
    except (ValueError, AttributeError):
        raise argparse.ArgumentTypeError("size must be WIDTHxHEIGHT, e.g. 1200x900")
    if width < 200 or height < 150:
        raise argparse.ArgumentTypeError("size is too small")
    return width, height


def _setup_logging(state_root: Path, verbose: bool) -> None:
    state_root.mkdir(parents=True, exist_ok=True)
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    logger = logging.getLogger("scadvariants")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s", "%H:%M:%S")
    if sys.stdout is not None:
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(fmt)
        logger.addHandler(stream)
    file_handler = RotatingFileHandler(
        state_root / "render.log",
        maxBytes=2_000_000,
        backupCount=2,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    logger.propagate = False


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Render every textual variant of a .scad file (or all .scad files "
            "in one folder) once and build an incremental gallery."
        )
    )
    p.add_argument(
        "--root",
        required=False,
        default=None,
        help="folder containing the .scad file(s); required for a render",
    )
    p.add_argument(
        "--state",
        default=None,
        help="logs/lock folder (default: <project>/state)",
    )
    p.add_argument(
        "--once",
        action="store_true",
        help="compatibility flag: rendering is always one-shot now",
    )
    p.add_argument("--force", action="store_true", help="re-render even cache hits")
    p.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="GLOB",
        help="only these relative globs (may be repeated)",
    )
    p.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="skip these relative globs (may be repeated)",
    )
    p.add_argument("--workers", type=int, default=2, help="parallel OpenSCAD renders")
    p.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="per-variant OpenSCAD timeout, seconds (default: 300)",
    )
    p.add_argument(
        "--slow-timeout",
        type=float,
        default=3600.0,
        help="timeout for delayed frame/assembly variants, seconds (default: 3600)",
    )
    p.add_argument("--max-variants", type=int, default=64)
    p.add_argument(
        "--mesh",
        dest="mesh",
        action="store_true",
        default=True,
        help="export STL together with PNG (default: on)",
    )
    p.add_argument(
        "--no-mesh",
        dest="mesh",
        action="store_false",
        help="render PNG previews only, without STL",
    )
    p.add_argument(
        "--stl-mode",
        choices=["printable", "all", "none"],
        default="printable",
        help=(
            "which variants get STL: printable (default; heavy ones delayed), "
            "all, or none"
        ),
    )
    p.add_argument("--no-pretty", action="store_true", help="keep raw OpenSCAD PNG")
    p.add_argument(
        "--no-notify",
        action="store_true",
        help="do not show Windows toast notifications after rendering",
    )
    p.add_argument(
        "--no-auto-open",
        action="store_true",
        help="do not auto-open the result gallery after rendering",
    )
    p.add_argument("--openscad", default=None, help="path to openscad executable")
    p.add_argument("--size", type=_parse_size, default=(1200, 900))
    p.add_argument("--camera", default="0,0,0,55,0,25,0")
    p.add_argument("--colorscheme", default="Tomorrow")
    p.add_argument("--projection", choices=["p", "o"], default="p")
    p.add_argument("--font", default=None, help="TTF font for image footers")
    p.add_argument("--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    # pythonw.exe has no console: sys.stdout/sys.stderr are None.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    args = _build_parser().parse_args(argv)
    if not args.root:
        print("error: --root is required", file=sys.stderr)
        return 2
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2
    state_root = (
        Path(args.state).expanduser().resolve()
        if args.state
        else _default_state()
    )
    if state_root == root or state_root in root.parents:
        print(
            "error: state folder must differ from and not contain the watched folder",
            file=sys.stderr,
        )
        return 2

    _setup_logging(state_root, args.verbose)
    logger = logging.getLogger("scadvariants")

    try:
        executable = find_openscad(args.openscad)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 2
    version = openscad_version(executable)
    width, height = args.size
    stl_mode = "none" if not args.mesh else args.stl_mode
    settings = RenderSettings(
        openscad=executable,
        width=width,
        height=height,
        camera=args.camera,
        colorscheme=args.colorscheme,
        projection=args.projection,
        mesh=stl_mode != "none",
        timeout=max(30.0, args.timeout),
        pretty=not args.no_pretty,
        font_path=args.font,
    )
    config = WatchConfig(
        root=root,
        state_root=state_root,
        settings=settings,
        openscad_version=version,
        workers=max(1, min(8, args.workers)),
        max_variants=max(1, args.max_variants),
        poll_interval=2.0,
        retry_interval=120.0,
        stl_mode=stl_mode,
        slow_timeout=max(30.0, args.slow_timeout),
        only=list(args.only),
        exclude=list(args.exclude),
        force=args.force,
        verbose=args.verbose,
        notify=not args.no_notify,
        auto_open_results=not args.no_auto_open,
    )
    watcher = Watcher(config)

    logger.info("scad-variants %s", APP_VERSION_DISPLAY)
    logger.info("OpenSCAD: %s", version)
    logger.info("root:   %s", root)
    logger.info("state:  %s", state_root)
    logger.info("STL:    %s", stl_mode)
    logger.info("started: %s", _now_iso())

    if args.once:
        logger.info("--once is the default mode; rendering once")
    try:
        stats = watcher.run_once()
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 2
    logger.info(
        "done: sources=%d rendered=%d skipped=%d failed=%d errors=%d",
        stats.sources,
        stats.rendered,
        stats.skipped,
        stats.failed,
        stats.errors,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
