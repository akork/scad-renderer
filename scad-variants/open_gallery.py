#!/usr/bin/env python3
"""Open a generated gallery HTML in an isolated browser window."""

from __future__ import annotations

import logging
import sys
import urllib.parse
from logging.handlers import RotatingFileHandler
from pathlib import Path

from scadvariants.browser import open_in_isolated
from scadvariants.gallery_server import open_gallery_page

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
    if len(args) != 1:
        show_error("Usage: open_gallery.py <index.html | scad-gallery:...>")
        return 2
    try:
        target = parse_target(args[0])
    except Exception as exc:
        show_error(f"Не удалось открыть галерею:\n\n{exc}")
        return 2
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


if __name__ == "__main__":
    raise SystemExit(main())
