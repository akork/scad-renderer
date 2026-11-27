#!/usr/bin/env python3
"""Assign an STL to a stable Orca slot.

Called by the scad-slot: protocol.  The browser cannot write arbitrary files,
so the native helper performs the copy and updates the slot page.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import urllib.parse
from logging.handlers import RotatingFileHandler
from pathlib import Path

from scadvariants.slots import assign_slot, delete_slot

PROJECT_DIR = Path(__file__).resolve().parent
STATE_DIR = PROJECT_DIR / "state"
LOG_PATH = STATE_DIR / "slots.log"
TOAST_SCRIPT = PROJECT_DIR / "scadvariants" / "show-toast.ps1"
LOG = logging.getLogger("scad-slot")


def setup_logging() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG.setLevel(logging.INFO)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=500_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s"))
    LOG.addHandler(handler)
    LOG.propagate = False


def show_error(message: str) -> None:
    LOG.error("%s", message)
    notify("Ошибка слота", message)


def notify(title: str, body: str) -> None:
    """Quiet toast: no console window, no focus change."""
    if sys.platform != "win32" or not TOAST_SCRIPT.is_file():
        return
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / (
        "System32/WindowsPowerShell/v1.0/powershell.exe"
    )
    if not powershell.is_file():
        return
    try:
        subprocess.Popen(
            [
                str(powershell),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(TOAST_SCRIPT),
                "-Title",
                title,
                "-Body",
                body[:500],
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            close_fds=True,
        )
    except Exception:
        LOG.debug("toast failed", exc_info=True)


def parse_uri(uri: str) -> tuple[str, str, Path | None]:
    parsed = urllib.parse.urlsplit(uri)
    if parsed.scheme.lower() != "scad-slot":
        raise ValueError(f"unsupported URI: {parsed.scheme}")
    action = (parsed.netloc or "assign").lower()
    if action not in {"assign", "delete"}:
        raise ValueError(f"unsupported action: {action}")
    query = urllib.parse.parse_qs(parsed.query)
    names = query.get("slot") or []
    if not names:
        raise ValueError("URI must contain slot")
    if action == "delete":
        return action, names[0], None
    files = query.get("stl") or []
    if not files:
        raise ValueError("URI must contain stl")
    return action, names[0], Path(files[0])


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        show_error("Usage: slot_action.py scad-slot://assign?... or scad-slot://delete?...")
        return 2
    try:
        action, name, stl = parse_uri(args[0])
        if action == "delete":
            target = delete_slot(name)
            LOG.info("slot %s deleted (%s)", name, target)
            notify("Слот удалён", f"{name}: {target}")
        else:
            target = assign_slot(name, stl)
            LOG.info("slot %s <- %s (%s)", name, stl, target)
            notify("Слот обновлён", f"{name}: {Path(str(stl)).name}")
    except Exception as exc:
        show_error(f"Не удалось обновить слот:\n\n{exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
