"""Automatic OpenSCAD variant renderer.

The package analyses top-level textual switches in ``.scad`` files, enumerates
their values, renders every combination, and caches results per variant.
"""

from .analyzer import (
    AnalysisError,
    ScadFile,
    Switch,
    analyze_scad,
    build_variants,
    dependency_closure,
    geometry_signature,
    variant_key,
)
from .watch import WatchConfig, Watcher

__all__ = [
    "AnalysisError",
    "ScadFile",
    "Switch",
    "analyze_scad",
    "build_variants",
    "dependency_closure",
    "geometry_signature",
    "variant_key",
    "WatchConfig",
    "Watcher",
]
