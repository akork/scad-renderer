"""Slicer adapter interface."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from . import windows

LOG = logging.getLogger("slicer-adapter")


@dataclass(frozen=True)
class SlicerAdapter:
    id: str
    display_name: str
    process_names: tuple[str, ...]
    candidates: tuple[Path, ...]
    supports_auto_reload: bool = True
    reload_hint: str = ""

    def detect(self) -> bool:
        return bool(windows.find_windows(self.process_names)) or any(
            candidate.is_file() for candidate in self.candidates
        )

    def open(self) -> None:
        windows_found = windows.find_windows(self.process_names)
        if windows_found:
            hwnd, pid, exe, title = windows_found[0]
            LOG.info("focus %s: pid=%s exe=%s title=%s", self.id, pid, exe, title)
            windows.focus_window(hwnd)
            return
        exe = next((candidate for candidate in self.candidates if candidate.is_file()), None)
        if exe is None:
            raise FileNotFoundError(f"{self.display_name} не найден.")
        LOG.info("launch %s: %s", self.id, exe)
        windows.launch(exe)
