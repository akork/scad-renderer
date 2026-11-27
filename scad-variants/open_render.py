#!/usr/bin/env python3
"""Open a render preview in the dedicated Edge browser, reusing its tab."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

from scadvariants.edge_preview import open_render  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        return 2
    return open_render(Path(args[0]))


if __name__ == "__main__":
    raise SystemExit(main())
