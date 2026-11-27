#!/usr/bin/env python3
"""Slicer integration dispatcher.

Protocol entry points:
  slicer_action.py open "scad-slicer://open?name=orca"
  slicer_action.py slot "scad-slot://assign?slot=left&stl=...&slicer=orca"

Slot storage is generic (see scadvariants.slots); focus/launch behaviour lives
in per-slicer adapters (see scadvariants.slicers).
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import urllib.parse
from logging.handlers import RotatingFileHandler
from pathlib import Path

from scadvariants.slicers import get_adapter
from scadvariants.slots import assign_slot, delete_slot

PROJECT_DIR = Path(__file__).resolve().parent
STATE_DIR = PROJECT_DIR / "state"
LOG_PATH = STATE_DIR / "slicer.log"
TOAST_SCRIPT = PROJECT_DIR / "scadvariants" / "show-toast.ps1"
LOG = logging.getLogger("scad-slicer")


def setup_logging() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG.setLevel(logging.INFO)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=500_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s"))
    LOG.addHandler(handler)
    LOG.propagate = False


def show_error(message: str) -> None:
    LOG.error("%s", message)
    notify("Ошибка слайсера", message)


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


def parse_open_uri(uri: str) -> str:
    parsed = urllib.parse.urlsplit(uri)
    if parsed.scheme.lower() != "scad-slicer":
        raise ValueError(f"unsupported URI scheme: {parsed.scheme!r}")
    query = urllib.parse.parse_qs(parsed.query)
    name = (query.get("name") or ["orca"])[0].strip().lower()
    get_adapter(name)
    return name


def parse_slot_uri(uri: str) -> tuple[str, str, str, Path | None]:
    parsed = urllib.parse.urlsplit(uri)
    if parsed.scheme.lower() != "scad-slot":
        raise ValueError(f"unsupported URI scheme: {parsed.scheme!r}")
    action = (parsed.netloc or "assign").lower()
    if action not in {"assign", "delete"}:
        raise ValueError(f"unsupported action: {action}")
    query = urllib.parse.parse_qs(parsed.query)
    names = query.get("slot") or []
    if not names:
        raise ValueError("URI must contain slot")
    slicer = (query.get("slicer") or ["orca"])[0].strip().lower()
    get_adapter(slicer)
    if action == "delete":
        return action, slicer, names[0], None
    files = query.get("stl") or []
    if not files:
        raise ValueError("URI must contain stl")
    return action, slicer, names[0], Path(files[0])


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = list(sys.argv[1:] if argv is None else argv)
    mode = ""
    if args and args[0] in {"open", "slot"}:
        mode = args.pop(0)
    if len(args) != 1:
        show_error(
            "Usage: slicer_action.py open <scad-slicer:...> "
            "| slot <scad-slot:...>"
        )
        return 2
    uri = args[0]
    if not mode:
        mode = "slot" if uri.lower().startswith("scad-slot:") else "open"

    try:
        if mode == "slot":
            action, slicer, name, stl = parse_slot_uri(uri)
            adapter = get_adapter(slicer)
            if action == "delete":
                target = delete_slot(name, slicer)
                LOG.info("slot %s/%s deleted (%s)", slicer, name, target)
                notify(f"Слот {adapter.display_name} удалён", f"{name}: {target}")
            else:
                target = assign_slot(name, stl, slicer)
                LOG.info("slot %s/%s <- %s (%s)", slicer, name, stl, target)
                notify(
                    f"Слот {adapter.display_name} обновлён",
                    f"{name}: {Path(str(stl)).name}",
                )
            return 0

        name = parse_open_uri(uri)
        adapter = get_adapter(name)
        adapter.open()
        return 0
    except Exception as exc:
        show_error(f"Не удалось выполнить действие слайсера:\n\n{exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
