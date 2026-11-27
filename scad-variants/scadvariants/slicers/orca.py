"""OrcaSlicer adapter."""

from __future__ import annotations

from pathlib import Path

from .base import SlicerAdapter

ORCA = SlicerAdapter(
    id="orca",
    display_name="OrcaSlicer",
    process_names=("orca-slicer.exe", "snapmaker-orca.exe"),
    candidates=(
        Path(r"C:\Program Files\OrcaSlicer\orca-slicer.exe"),
        Path(r"C:\Program Files\Snapmaker_Orca\snapmaker-orca.exe"),
    ),
    supports_auto_reload=True,
    reload_hint="В Orca выбери Reload from disk.",
)
