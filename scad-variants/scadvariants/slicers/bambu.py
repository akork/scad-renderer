"""Bambu Studio adapter."""

from __future__ import annotations

from pathlib import Path

from .base import SlicerAdapter

BAMBU = SlicerAdapter(
    id="bambu",
    display_name="Bambu Studio",
    process_names=("bambu-studio.exe", "bambustudio.exe"),
    candidates=(
        Path(r"C:\Program Files\Bambu Studio\bambu-studio.exe"),
        Path(r"C:\Program Files\Bambu Studio\BambuStudio.exe"),
        Path(r"C:\Program Files (x86)\Bambu Studio\bambu-studio.exe"),
        Path(r"C:\Program Files (x86)\Bambu Studio\BambuStudio.exe"),
    ),
    supports_auto_reload=False,
    reload_hint="В Bambu Studio импортируй STL из слота вручную.",
)
