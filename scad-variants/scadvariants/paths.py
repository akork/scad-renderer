"""Application roots that work both from source and from a frozen EXE."""

from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """Return the folder that owns runtime data.

    Source checkout: the repository root above ``scad-variants``.
    Frozen EXE: the folder containing the executable.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def resource_root() -> Path:
    """Return bundled read-only resources (viewer scripts) for this run."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[2]
