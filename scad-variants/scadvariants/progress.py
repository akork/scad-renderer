from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .paths import app_root

LOG = logging.getLogger(__name__)

# The tray icon reads this directory from every renderer process, including
# one-shot context-menu renders that use a temporary state folder.
DEFAULT_PROGRESS_DIR = app_root() / "scad-variants" / "state" / "progress"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class ProgressWriter:
    """Atomically publish the progress of one active render task."""

    def __init__(
        self,
        *,
        source: Path,
        out_dir: Path,
        total: int,
        rel: str = "",
        progress_dir: Path | None = None,
    ) -> None:
        self.path = (progress_dir or DEFAULT_PROGRESS_DIR) / (
            uuid.uuid4().hex + ".json"
        )
        self._lock = threading.Lock()
        self.data: dict[str, Any] = {
            "schema": 1,
            "id": self.path.stem,
            "pid": os.getpid(),
            "source": str(source),
            "name": Path(source).name,
            "rel": rel,
            "out_dir": str(out_dir),
            "total": max(0, int(total)),
            "done": 0,
            "current": "",
            "current_started": "",
            "current_estimate_s": 0,
            "status": "running",
            "started": _now(),
            "updated": _now(),
        }
        self._write()

    def start_variant(self, current: str, estimate: float | None = None) -> None:
        with self._lock:
            self.data["current"] = current
            self.data["current_started"] = _now()
            try:
                estimate_value = float(estimate or 0)
            except (TypeError, ValueError):
                estimate_value = 0
            self.data["current_estimate_s"] = max(0, estimate_value)
            self.data["updated"] = _now()
            self._write()

    def _write(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            temp.write_text(
                json.dumps(self.data, ensure_ascii=False),
                encoding="utf-8",
            )
            os.replace(temp, self.path)
        except OSError:
            # Progress reporting must never break the actual render.
            LOG.debug("could not write progress file %s", self.path)

    def advance(self, current: str = "") -> None:
        with self._lock:
            total = int(self.data.get("total") or 0)
            done = min(total, int(self.data.get("done") or 0) + 1)
            self.data["done"] = done
            self.data["current"] = ""
            self.data["current_started"] = ""
            self.data["current_estimate_s"] = 0
            self.data["updated"] = _now()
            self._write()

    def finish(self) -> None:
        with self._lock:
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                LOG.debug("could not remove progress file %s", self.path)
