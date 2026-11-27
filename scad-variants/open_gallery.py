#!/usr/bin/env python3
"""Open SCAD galleries, previews and the 3D viewer.

Modes:
  open_gallery.py <index.html | scad-gallery:...>
  open_gallery.py --reuse-tab <index.html>
  open_gallery.py --viewer <scad-viewer:...>
  open_gallery.py --ensure <scad-embed:...>
"""

from __future__ import annotations

import logging
import sys
import urllib.parse
from logging.handlers import RotatingFileHandler
from pathlib import Path

from scadvariants.browser import open_in_isolated
from scadvariants.edge_preview import open_render as open_existing_render
from scadvariants.gallery_server import (
    DEFAULT_PORT,
    ensure_server,
    open_gallery_page,
    viewer_url,
)

PROJECT_DIR = Path(__file__).resolve().parent
STATE_DIR = PROJECT_DIR / "state"
LOG_PATH = STATE_DIR / "gallery.log"
LOG = logging.getLogger("scad-gallery")


def setup_logging() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG.setLevel(logging.INFO)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=500_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s"))
    LOG.addHandler(handler)
    LOG.propagate = False


def allowed(path: Path) -> bool:
    roots = [
        (Path.home() / "Downloads").resolve(),
        PROJECT_DIR.parent.resolve(),
    ]
    return any(path == root or root in path.parents for root in roots)


def parse_target(arg: str) -> Path:
    if arg.lower().startswith("scad-gallery:"):
        parsed = urllib.parse.urlsplit(arg)
        query = urllib.parse.parse_qs(parsed.query)
        values = query.get("path") or []
        if not values:
            raise ValueError("URI has no path")
        target = Path(values[0]).expanduser().resolve()
    else:
        target = Path(arg).expanduser().resolve()
    if target.suffix.lower() not in {".html", ".htm"} or not target.is_file():
        raise ValueError(f"not an HTML file: {target}")
    if not allowed(target):
        raise ValueError(f"path is outside allowed roots: {target}")
    return target


def parse_viewer(arg: str) -> tuple[Path, str]:
    parsed = urllib.parse.urlsplit(arg)
    if parsed.scheme.lower() != "scad-viewer":
        raise ValueError(f"unsupported URI scheme: {parsed.scheme!r}")
    query = urllib.parse.parse_qs(parsed.query)
    folders = query.get("folder") or []
    models = query.get("model") or []
    if not folders or not models:
        raise ValueError("URI must contain folder and model")
    folder = Path(folders[0]).expanduser().resolve()
    model = (folder / Path(models[0]).name).resolve()
    if not folder.is_dir():
        raise ValueError(f"folder not found: {folder}")
    if model.suffix.lower() != ".stl" or not model.is_file():
        raise ValueError(f"STL not found: {model}")
    if not allowed(folder):
        raise ValueError(f"folder is outside allowed roots: {folder}")
    if model.parent != folder:
        raise ValueError("model is outside the requested folder")
    return folder, model.name


def ensure_embed(arg: str) -> None:
    parsed = urllib.parse.urlsplit(arg)
    if parsed.scheme.lower() != "scad-embed":
        raise ValueError(f"unsupported URI scheme: {parsed.scheme!r}")
    ensure_server(DEFAULT_PORT)


def show_error(message: str) -> None:
    LOG.error("%s", message)
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, "SCAD gallery", 0x10)
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = list(sys.argv[1:] if argv is None else argv)
    mode = "gallery"
    if args and args[0] in {"--reuse-tab", "--viewer", "--ensure"}:
        mode = args[0][2:]
        args = args[1:]
    if len(args) != 1:
        show_error(
            "Usage: open_gallery.py "
            "[--reuse-tab|--viewer|--ensure] <index.html | scad-gallery:...>"
        )
        return 2

    if mode == "ensure":
        try:
            ensure_embed(args[0])
        except Exception as exc:
            LOG.exception("could not ensure gallery server")
            return 2
        return 0

    try:
        if mode == "viewer":
            folder, model_name = parse_viewer(args[0])
            url = viewer_url(folder, model_name)
            LOG.info("open viewer: %s", url)
            if not open_in_isolated(url, profile_name="browser-profile"):
                show_error(f"Не удалось открыть 3D-просмотр:\n\n{url}")
                return 1
            return 0

        target = parse_target(args[0])
        if mode == "reuse-tab":
            LOG.info("reuse preview tab: %s", target)
            return open_existing_render(target)

        LOG.info("open gallery: %s", target)
        try:
            if open_gallery_page(target):
                return 0
        except Exception:
            LOG.exception("gallery server failed; falling back to file")
        if not open_in_isolated(
            target,
            profile_name="browser-profile",
            app_mode=False,
        ):
            show_error(f"Не удалось открыть галерею:\n\n{target}")
            return 1
        return 0
    except Exception as exc:
        show_error(f"Не удалось открыть страницу:\n\n{exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
