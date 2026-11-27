"""Slicer-specific adapters.

The slot store is slicer-agnostic; each adapter knows how to find, focus or
launch its slicer and what kind of stable slot file it expects.
"""

from __future__ import annotations

from .base import SlicerAdapter
from .bambu import BAMBU
from .orca import ORCA

ADAPTERS: dict[str, SlicerAdapter] = {
    ORCA.id: ORCA,
    BAMBU.id: BAMBU,
}


def get_adapter(name: str) -> SlicerAdapter:
    key = (name or "orca").strip().lower()
    try:
        return ADAPTERS[key]
    except KeyError as exc:
        raise ValueError(f"Неизвестный слайсер: {name}") from exc


def choices() -> list[SlicerAdapter]:
    return list(ADAPTERS.values())
