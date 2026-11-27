#!/usr/bin/env python3
"""Ensure the local gallery/3D server is running, without opening a browser."""

from __future__ import annotations

import sys
import urllib.parse
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

from scadvariants.gallery_server import DEFAULT_PORT, ensure_server  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        return 2
    parsed = urllib.parse.urlsplit(args[0])
    if parsed.scheme.lower() != "scad-embed":
        return 2
    try:
        ensure_server(DEFAULT_PORT)
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
