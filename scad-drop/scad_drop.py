#!/usr/bin/env python3
"""Render one .scad file in place from the Explorer context menu.

The ``scad-variants`` pipeline is invoked once with the selected file's parent
as ``--root`` and an exact-name ``--only`` filter. Results are written next to
the source file; no folder is copied to or watched.
"""

from __future__ import annotations

import argparse
import ctypes
import logging
import os
import shutil
import subprocess
import sys
import time
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_NAME = "scad-drop"
DEFAULT_RENDER_TIMEOUT = 3600.0
DEFAULT_POLL = 2.0

PROJECT_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = PROJECT_DIR.parent
DEFAULT_TOOL = WORKSPACE_DIR / "scad-variants" / "scad_variants.py"
DEFAULT_RENDERER_STATE = WORKSPACE_DIR / "scad-variants" / "state"
DEFAULT_STATE = PROJECT_DIR / "state"

LOG = logging.getLogger(APP_NAME)


def _read_app_version() -> tuple[str, int]:
    root = PROJECT_DIR.parent
    try:
        value = (root / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "1.0.0", 0
    try:
        build = int((root / "BUILD").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        build = 0
    return (value or "1.0.0"), max(0, build)


APP_VERSION, APP_BUILD = _read_app_version()
APP_VERSION_DISPLAY = f"{APP_VERSION}-dev.{APP_BUILD}" if APP_BUILD else APP_VERSION


def _setup_logging(state_root: Path, verbose: bool) -> None:
    state_root.mkdir(parents=True, exist_ok=True)
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    LOG.setLevel(logging.DEBUG if verbose else logging.INFO)
    LOG.handlers.clear()
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s")
    if sys.stdout is not None:
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(fmt)
        LOG.addHandler(stream)
    handler = RotatingFileHandler(
        state_root / "scad_drop.log",
        maxBytes=1_000_000,
        backupCount=2,
        encoding="utf-8",
    )
    handler.setFormatter(fmt)
    LOG.addHandler(handler)
    LOG.propagate = False


def _glob_exact(name: str) -> str:
    escaped = []
    for char in name:
        if char in "*?[":
            escaped.append("[" + char + "]")
        else:
            escaped.append(char)
    return "".join(escaped)


def gallery_dir(target: Path) -> Path:
    return target.parent / f"{target.stem}_renders"


def wait_for_gallery(target: Path, timeout: float, poll: float) -> Path | None:
    index = gallery_dir(target) / "index.html"
    deadline = time.monotonic() + max(1.0, timeout)
    while time.monotonic() < deadline:
        if index.is_file():
            return index
        time.sleep(max(0.25, poll))
    return None


def show_error(message: str) -> None:
    LOG.error("%s", message)
    if os.name != "nt":
        return
    try:
        ctypes.windll.user32.MessageBoxW(None, message, "SCAD — ошибка", 0x10)
    except Exception:
        pass


def open_gallery(index: Path) -> None:
    try:
        variants_dir = str(WORKSPACE_DIR / "scad-variants")
        if variants_dir not in sys.path:
            sys.path.insert(0, variants_dir)
        from scadvariants.browser import auto_open_results_enabled
        from scadvariants.gallery_server import open_gallery_page

        if not auto_open_results_enabled():
            LOG.info("result auto-open is disabled")
            return
        if open_gallery_page(index):
            return
    except Exception:
        LOG.exception("isolated gallery open failed for %s", index)
    try:
        if os.name == "nt":
            os.startfile(str(index))
        else:
            subprocess.Popen(["xdg-open", str(index)])
    except Exception:
        LOG.exception("could not open %s", index)


def render_one_file(
    source: Path,
    tool: Path,
    renderer_state: Path,
    timeout: float,
    open_result: bool = True,
) -> int:
    """Render one .scad file in place (Explorer context-menu mode)."""
    source = Path(source).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".scad":
        message = f"Это не файл .scad:\n{source}"
        LOG.error("%s", message)
        show_error(message)
        return 2
    if not tool.is_file():
        message = f"Не найден scad_variants.py:\n{tool}"
        LOG.error("%s", message)
        show_error(message)
        return 2

    temp_state = renderer_state / f"context-{uuid.uuid4().hex[:8]}"
    temp_state.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-u",
        str(tool),
        "--once",
        "--root",
        str(source.parent),
        "--state",
        str(temp_state),
        "--only",
        _glob_exact(source.name),
        "--force",
        "--no-auto-open",
    ]
    LOG.info("context render: %s", source)
    try:
        returncode = subprocess.call(command, cwd=str(tool.parent))
    except Exception as exc:
        LOG.exception("could not start context render for %s", source)
        shutil.rmtree(temp_state, ignore_errors=True)
        show_error(f"Не удалось запустить рендеринг:\n\n{source}\n\n{exc}")
        return 1

    if returncode != 0:
        shutil.rmtree(temp_state, ignore_errors=True)
        LOG.error("context render failed for %s (exit %s)", source, returncode)
        show_error(
            "Рендеринг завершился ошибкой.\n\n"
            f"{source}\n\n"
            "Подробности — в scad_drop.log."
        )
        return returncode

    index = wait_for_gallery(source, timeout, DEFAULT_POLL)
    shutil.rmtree(temp_state, ignore_errors=True)
    if index is None:
        LOG.error("context gallery timeout: %s", source)
        show_error(
            "Рендеринг завершился, но каталог _renders не появился.\n\n"
            f"{source}"
        )
        return 1

    LOG.info("context gallery ready: %s", index)
    if open_result:
        open_gallery(index)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render one .scad file in place (Explorer context-menu mode)."
    )
    parser.add_argument("--tool", default=str(DEFAULT_TOOL), help="path to scad_variants.py")
    parser.add_argument(
        "--renderer-state",
        default=str(DEFAULT_RENDERER_STATE),
        help="state folder for temporary render state",
    )
    parser.add_argument(
        "--state",
        default=str(DEFAULT_STATE),
        help="state folder for this helper (default: <project>/state)",
    )
    parser.add_argument(
        "--render-file",
        metavar="PATH",
        required=True,
        help="render one .scad file in place and exit",
    )
    parser.add_argument(
        "--render-timeout",
        type=float,
        default=DEFAULT_RENDER_TIMEOUT,
        help="seconds to wait for a render/gallery",
    )
    parser.add_argument(
        "--no-open",
        "--no-gallery",
        dest="open",
        action="store_false",
        default=True,
        help="do not open the HTML gallery after rendering",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    args = _build_parser().parse_args(argv)
    args.tool = Path(args.tool).expanduser().resolve()
    args.renderer_state = Path(args.renderer_state).expanduser().resolve()
    args.state = Path(args.state).expanduser().resolve()

    _setup_logging(args.state, args.verbose)
    LOG.info("%s %s", APP_NAME, APP_VERSION_DISPLAY)
    return render_one_file(
        Path(args.render_file),
        args.tool,
        args.renderer_state,
        args.render_timeout,
        open_result=args.open,
    )


if __name__ == "__main__":
    raise SystemExit(main())
