from __future__ import annotations

import fnmatch
import hashlib
import json
import logging
import os
import shutil
import struct
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from .analyzer import (
    ScadFile,
    analyze_scad,
    build_variants,
    dependency_closure,
    geometry_signature,
    variant_key,
    variant_stem,
)
from .gallery import write_source_page
from .notify import notify_render
from .progress import ProgressWriter
from .render import RenderSettings, make_contact_sheet, render_variant
from .browser import auto_open_results_enabled
from .gallery_server import open_gallery_page

LOG = logging.getLogger("scadvariants")

APP_VERSION = "1.0"

# Values that are valid exports but very expensive to evaluate.  They are not
# skipped: the size sorter puts them near the front when no previous STL size
# is known, and the slow timeout still applies to them.
STL_DELAY_VALUES = {
    "frame",
    "assembly",
    "section",
    "side",
    "comb_strip",
    "body",
}


def _stl_triangles(path: Path) -> int:
    """Triangle count from binary or ASCII STL; 0 if unreadable."""
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            head = handle.read(84)
            if len(head) == 84:
                binary_count = struct.unpack("<I", head[80:84])[0]
                if 84 + binary_count * 50 == size:
                    return binary_count
            handle.seek(0)
            count = 0
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    return count
                count += chunk.count(b"facet normal")
    except OSError:
        return 0


def _complexity(
    item: tuple[Any, Path, Path | None, str, bool],
    previous: dict[str, dict[str, Any]],
    out_dir: Path,
) -> tuple[int, int, float, int]:
    """Sort key: biggest triangle count / STL first.

    Existing STL files give an exact triangle count.  For a brand-new variant
    there is no geometry yet, so the old "heavy value" flag is the fallback.
    """
    variant, _image_path, stl_path, _key, delayed = item
    old = previous.get(variant.variant_id) or {}
    triangles = int(old.get("triangles") or 0)
    stl_bytes = int(old.get("stl_bytes") or 0)
    stl_name = old.get("stl")
    candidate = out_dir / str(stl_name) if stl_name else stl_path
    if candidate and candidate.is_file():
        if not triangles:
            triangles = _stl_triangles(candidate)
        if not stl_bytes:
            try:
                stl_bytes = candidate.stat().st_size
            except OSError:
                stl_bytes = 0
    duration = float(old.get("duration_s") or 0.0)
    return (triangles, stl_bytes, duration, 1 if delayed else 0)


def _stl_plan(source_rel: str, values: dict[str, str], mode: str) -> tuple[bool, bool]:
    """Return (needs_stl, delayed)."""
    if mode == "none":
        return False, False
    delayed = any(str(value).lower() in STL_DELAY_VALUES for value in values.values())
    if mode == "all":
        return True, delayed
    # "printable" / default mode: still skip 2D wrappers and preview-only views.
    stem = Path(source_rel).stem.lower()
    if stem.startswith("section") or stem.startswith("show_"):
        return False, False
    if stem.startswith("preview"):
        p_value = values.get("p")
        if p_value is not None and p_value.lower() != "h":
            return False, False
    return True, delayed


def _assign_group_names(variants: list[Any], groups: list[dict[str, Any]]) -> None:
    """Choose output names using only switches that actually matter.

    A switch that varies inside a geometry group is irrelevant for that group
    and is omitted from its file name. Switches that never change geometry are
    omitted globally. This yields, for example:
        part-frame (side/lid_style dropped)
        part-lid__lid_style-hex (side dropped)
        part-rail__side-left (lid_style dropped)
    """
    if not variants:
        return
    names = list(variants[0].values.keys())
    sig_by_id = {
        member.variant_id: group["sig"]
        for group in groups
        for member in group["members"]
    }

    globally_relevant: dict[str, bool] = {}
    for name in names:
        buckets: dict[tuple[tuple[str, str], ...], set[str]] = {}
        for variant in variants:
            key = tuple(
                (key_name, value)
                for key_name, value in variant.values.items()
                if key_name != name
            )
            buckets.setdefault(key, set()).add(sig_by_id[variant.variant_id])
        globally_relevant[name] = any(len(sigs) > 1 for sigs in buckets.values())

    used: set[str] = set()
    for group in groups:
        members = group["members"]
        varying = {
            name
            for name in names
            if len({member.values[name] for member in members}) > 1
        }
        keep = [
            name
            for name in names
            if globally_relevant.get(name, False) and name not in varying
        ]
        effective = {name: group["rep"].values[name] for name in keep}
        stem = variant_stem(effective)
        if stem in used:
            stem = f"{stem}-{group['sig'][:6]}"
        used.add(stem)
        group["stem"] = stem
        group["effective_values"] = effective
        group["effective_label"] = (
            " · ".join(f'{name} = "{value}"' for name, value in effective.items())
            or "по умолчанию"
        )


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _variants_word(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return f"{count} вариант"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return f"{count} варианта"
    return f"{count} вариантов"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = path.parent / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    tmp = temp_dir / f".{path.name}.{uuid.uuid4().hex[:8]}.tmp"
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _file_digest(path: Path) -> str:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return "<missing>"


def _safe_unlink(path: Path, boundary: Path) -> None:
    try:
        resolved = path.resolve()
        boundary = boundary.resolve()
        if boundary == resolved or boundary in resolved.parents:
            path.unlink(missing_ok=True)
    except OSError:
        pass


def _clean_tmp(directory: Path) -> None:
    """Remove the transient folder after a successful/failed pass."""
    for name in ("tmp", "TMP"):
        path = directory / name
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)


@dataclass(slots=True)
class WatchConfig:
    root: Path
    state_root: Path
    settings: RenderSettings
    openscad_version: str
    workers: int = 2
    max_variants: int = 64
    poll_interval: float = 2.0
    retry_interval: float = 120.0
    stl_mode: str = "printable"
    slow_timeout: float = 3600.0
    only: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    force: bool = False
    verbose: bool = False
    notify: bool = True
    auto_open_results: bool = True
    progress_dir: Path | None = None

    @property
    def render_key_config(self) -> dict[str, Any]:
        return {
            "app": APP_VERSION,
            "openscad": self.openscad_version,
            "png": self.settings.png_config(),
            "mesh": bool(self.settings.mesh),
            "stl_mode": self.stl_mode,
            "stl": self.settings.stl_config() if self.settings.mesh else None,
        }


class InstanceLock:
    """Cross-process lock so two watchers cannot fight over the same folder."""

    def __init__(self, path: Path):
        self.path = path
        self.handle = None
        self.os_name = os.name

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.handle = self.path.open("a+b")
            self.handle.seek(0)
            try:
                empty = self.handle.read(1) == b""
            except PermissionError as exc:
                # A locked byte range also blocks reads.  Do not truncate or
                # write here: that can destroy the other process's lock.
                raise RuntimeError(
                    f"another watcher already uses {self.path.parent}"
                ) from exc
            if empty:
                self.handle.write(b"0")
                self.handle.flush()
            self.handle.seek(0)
            if self.os_name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except RuntimeError:
            if self.handle is not None:
                try:
                    self.handle.close()
                except OSError:
                    pass
                self.handle = None
            raise
        except (OSError, IOError) as exc:
            if self.handle is not None:
                try:
                    self.handle.close()
                except OSError:
                    pass
                self.handle = None
            raise RuntimeError(
                f"another watcher already uses {self.path.parent}"
            ) from exc

    def release(self) -> None:
        if not self.handle:
            return
        try:
            self.handle.seek(0)
            if self.os_name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self.handle.close()
        self.handle = None


@dataclass
class CycleStats:
    sources: int = 0
    rendered: int = 0
    skipped: int = 0
    failed: int = 0
    errors: int = 0


class Watcher:
    def __init__(self, config: WatchConfig):
        self.config = config
        self.root = config.root.resolve()
        self.state_root = config.state_root.resolve()
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.source_dirs: dict[Path, Path] = {}
        self.dependency_map: dict[Path, list[Path]] = {}
        self.fingerprints: dict[Path, str] = {}
        self.lock = InstanceLock(self.state_root / ".watch.lock")
        self._first_cycle = True
        self._force_once = config.force
        self._stop = threading.Event()

    # -- discovery ---------------------------------------------------------

    def _allowed(self, rel: str) -> bool:
        rel_posix = rel.replace("\\", "/")
        if any(
            part in {".git", ".hg", ".svn", "node_modules", ".scad-variants"}
            for part in rel_posix.split("/")
        ):
            return False
        if any(
            fnmatch.fnmatch(rel_posix, pat) or fnmatch.fnmatch(rel_posix.lower(), pat.lower())
            for pat in self.config.exclude
        ):
            return False
        if self.config.only:
            return any(
                fnmatch.fnmatch(rel_posix, pat)
                or fnmatch.fnmatch(rel_posix.lower(), pat.lower())
                for pat in self.config.only
            )
        return True

    def discover_sources(self) -> list[Path]:
        out: list[Path] = []
        skip_dirs = {".git", ".hg", ".svn", "node_modules", ".scad-variants"}

        def onerror(exc: OSError) -> None:  # unreadable folder: skip it
            LOG.debug("skipping unreadable folder: %s", exc)

        for dirpath, dirnames, filenames in os.walk(
            self.root, topdown=True, onerror=onerror, followlinks=False
        ):
            current = Path(dirpath)
            if current.resolve() == self.state_root:
                dirnames[:] = []
                continue
            dirnames[:] = [
                d
                for d in dirnames
                if d not in skip_dirs
                and not d.lower().endswith("_renders")
                and (current / d).resolve() != self.state_root
            ]
            for filename in filenames:
                if Path(filename).suffix.lower() != ".scad":
                    continue
                path = current / filename
                if ".tmp." in path.name or path.name.startswith("~$"):
                    continue
                try:
                    rel = path.relative_to(self.root)
                    if not self._allowed(rel.as_posix()):
                        continue
                    if path.is_file():
                        out.append(path.resolve())
                except (OSError, ValueError):
                    continue
        out.sort(key=lambda p: str(p).lower())
        return out

    def source_dir(self, source: Path) -> Path:
        """Output folder next to the source: my_part.scad -> my_part_renders/."""
        return source.parent / f"{source.stem}_renders"

    # -- fingerprints ------------------------------------------------------

    def _fingerprint_from(
        self, source_digest: str, dependency_digests: Iterable[tuple[Path, str]]
    ) -> str:
        h = hashlib.sha256()
        h.update(source_digest.encode())
        for dep, digest in dependency_digests:
            h.update(b"\x1e")
            h.update(str(dep).encode("utf-8", "surrogatepass"))
            h.update(b"\x1f")
            h.update(digest.encode())
        return h.hexdigest()

    def _fingerprint(self, source: Path) -> str:
        return self._fingerprint_from(
            _file_digest(source),
            ((dep, _file_digest(dep)) for dep in self.dependency_map.get(source, [])),
        )

    # -- rendering ---------------------------------------------------------

    def _render_key(
        self, scad: ScadFile, values: dict[str, str], with_stl: bool
    ) -> str:
        deps = dependency_closure(scad.dependencies)
        cache: dict[Path, bytes] = {}
        config = dict(self.config.render_key_config)
        config["variant_stl"] = bool(with_stl)
        return variant_key(
            scad,
            values,
            deps,
            config,
            dependency_cache=cache,
        )

    def _manifest_source(self, source: Path) -> dict[str, str]:
        return {
            "abs": str(source),
            "rel": source.relative_to(self.root).as_posix(),
        }

    def _error_manifest(
        self,
        source: Path,
        previous: dict[str, Any] | None,
        error: str,
    ) -> dict[str, Any]:
        now = _now_iso()
        if previous:
            manifest = dict(previous)
        else:
            manifest = {
                "schema": 1,
                "source": self._manifest_source(source),
                "switches": [],
                "variants": [],
            }
        manifest["status"] = "error"
        manifest["error"] = error
        manifest["updated_at"] = now
        manifest["retry_after"] = (
            datetime.now().astimezone() + timedelta(seconds=self.config.retry_interval)
        ).isoformat(timespec="seconds")
        return manifest

    def process_source(self, source: Path, force: bool = False) -> CycleStats:
        stats = CycleStats(sources=1)
        source = source.resolve()
        out_dir = self.source_dir(source)
        manifest_path = out_dir / "manifest.json"
        previous = _load_json(manifest_path)
        _clean_tmp(out_dir)
        rel = source.relative_to(self.root).as_posix()
        started = time.time()
        source_digest_before = _file_digest(source)

        try:
            scad = analyze_scad(source)
            variants = build_variants(scad.switches, self.config.max_variants)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            LOG.error("[%s] analysis failed: %s", rel, error)
            manifest = self._error_manifest(source, previous, error)
            _atomic_json(manifest_path, manifest)
            write_source_page(out_dir, manifest)
            _clean_tmp(out_dir)
            stats.errors += 1
            # Remember the exact bytes we tried to analyse, not a later save.
            self.fingerprints[source] = self._fingerprint_from(
                source_digest_before,
                (
                    (dep, _file_digest(dep))
                    for dep in self.dependency_map.get(source, [])
                ),
            )
            return stats

        deps_all = dependency_closure(scad.dependencies)
        self.dependency_map[source] = deps_all
        dep_digests = [(dep, _file_digest(dep)) for dep in deps_all]
        prev_variants: dict[str, dict[str, Any]] = {}
        if previous:
            for item in previous.get("variants") or []:
                if isinstance(item, dict) and item.get("id"):
                    prev_variants[str(item["id"])] = item

        duration_by_id: dict[str, float] = {}
        for variant_id, item in prev_variants.items():
            try:
                duration = float(item.get("duration_s") or 0)
            except (TypeError, ValueError):
                continue
            if duration > 0:
                duration_by_id[variant_id] = duration

        # Different switch combinations often produce exactly the same model
        # (e.g. lid_style is irrelevant for the frame).  Render each unique
        # geometry once and let the aliases point at the same files.
        dep_cache: dict[Path, bytes] = {}
        grouped: dict[str, list[Any]] = {}
        for variant in variants:
            sig = geometry_signature(
                scad, variant.values, deps_all, dependency_cache=dep_cache
            )
            grouped.setdefault(sig, []).append(variant)

        groups: list[dict[str, Any]] = []
        for sig, members in grouped.items():
            plans = [
                _stl_plan(rel, v.values, self.config.stl_mode) for v in members
            ]
            with_stl = bool(self.config.settings.mesh and any(n for n, _ in plans))
            delayed = any(d for n, d in plans if n)
            groups.append(
                {
                    "sig": sig,
                    "rep": members[0],
                    "members": members,
                    "with_stl": with_stl,
                    "delayed": delayed,
                }
            )
        _assign_group_names(variants, groups)
        groups.sort(
            key=lambda group: _complexity(
                (
                    group["rep"],
                    out_dir / f"{group['stem']}.png",
                    out_dir / f"{group['stem']}.stl",
                    "",
                    bool(group["delayed"]),
                ),
                prev_variants,
                out_dir,
            ),
            reverse=True,
        )

        tasks: list[tuple[Any, Path, Path | None, str, bool]] = []
        entries: dict[str, dict[str, Any]] = {}
        planned_stl_ids: set[str] = set()
        label_by_rep = {
            group["rep"].variant_id: group["effective_label"] for group in groups
        }
        for group in groups:
            variant = group["rep"]
            with_stl = bool(group["with_stl"])
            delayed = bool(group["delayed"])
            stem = str(group["stem"])
            old = prev_variants.get(variant.variant_id)
            image_rel = Path(f"{stem}.png")
            image_path = out_dir / image_rel
            stl_rel = Path(f"{stem}.stl")
            stl_path = out_dir / stl_rel
            if with_stl:
                planned_stl_ids.add(stem)
            # One-time migration when a switch becomes irrelevant and the
            # output name changes.  Preserve the existing render instead of
            # redoing the expensive geometry evaluation.
            if old:
                old_image = old.get("image")
                if old_image and not image_path.is_file():
                    old_path = out_dir / str(old_image)
                    if old_path.is_file():
                        os.replace(old_path, image_path)
                old_stl = old.get("stl")
                if with_stl and old_stl and not stl_path.is_file():
                    old_path = out_dir / str(old_stl)
                    if old_path.is_file():
                        os.replace(old_path, stl_path)
            key = self._render_key(scad, variant.values, with_stl)
            cached = (
                not force
                and old is not None
                and old.get("key") == key
                and old.get("status") != "error"
                and image_path.is_file()
                and (not with_stl or stl_path.is_file())
            )

            base: dict[str, Any] = {
                "id": variant.variant_id,
                "values": dict(variant.values),
                "label": group["effective_label"],
                "stem": stem,
                "effective_values": dict(group["effective_values"]),
                "stl_planned": with_stl,
                "delayed": delayed,
                "geometry": group["sig"],
                "aliases": [
                    v.variant_id for v in group["members"] if v is not variant
                ],
            }
            if cached and old is not None:
                entry = dict(old)
                entry.update(base)
                entry["status"] = "ok"
                entry["image"] = image_rel.as_posix()
                entry["stl"] = (
                    stl_rel.as_posix()
                    if with_stl and stl_path.is_file()
                    else None
                )
                entries[variant.variant_id] = entry
                stats.skipped += 1
            else:
                entries[variant.variant_id] = {
                    **base,
                    "status": "pending",
                    "image": image_rel.as_posix() if image_path.is_file() else None,
                    "stl": (
                        stl_rel.as_posix()
                        if with_stl and stl_path.is_file()
                        else None
                    ),
                    **(
                        {
                            "key": old.get("key"),
                            "rendered_at": old.get("rendered_at"),
                            "duration_s": old.get("duration_s"),
                        }
                        if old
                        else {}
                    ),
                }
                tasks.append(
                    (
                        variant,
                        image_path,
                        stl_path if with_stl else None,
                        key,
                        delayed,
                    )
                )

        if tasks:
            progress = ProgressWriter(
                source=source,
                out_dir=out_dir,
                total=len(tasks),
                rel=str(rel),
                progress_dir=self.config.progress_dir,
            )
        else:
            progress = None

        if tasks:
            delayed_count = sum(1 for task in tasks if task[4])
            LOG.info(
                "[%s] rendering %d unique of %d variant(s)%s...",
                rel,
                len(tasks),
                len(variants),
                (
                    f" ({delayed_count} heavy)"
                    if delayed_count
                    else ""
                ),
            )

        def work(item):
            variant, image_path, stl_path, key, delayed = item
            if progress is not None:
                progress.start_variant(
                    str(variant.label),
                    duration_by_id.get(variant.variant_id),
                )
            render_settings = self.config.settings
            if delayed and self.config.slow_timeout > render_settings.timeout:
                render_settings = replace(
                    render_settings, timeout=self.config.slow_timeout
                )
            result = render_variant(
                source=source,
                values=variant.values,
                image_path=image_path,
                stl_path=stl_path,
                label=label_by_rep.get(variant.variant_id, variant.label),
                subtitle=rel,
                settings=render_settings,
            )
            return variant, image_path, stl_path, key, delayed, result

        def mark_done(item):
            if progress is not None:
                progress.advance(str(item[0].label))

        def run_batch(batch):
            out = []
            if not batch:
                return out
            if self.config.workers <= 1:
                for item in batch:
                    try:
                        out.append(work(item))
                    finally:
                        mark_done(item)
            else:
                with ThreadPoolExecutor(max_workers=self.config.workers) as pool:
                    future_items = {
                        pool.submit(work, item): item for item in batch
                    }
                    for future in as_completed(future_items):
                        item = future_items[future]
                        try:
                            out.append(future.result())
                        except Exception:  # pragma: no cover - defensive
                            LOG.exception("[%s] render worker crashed", rel)
                            stats.failed += 1
                        finally:
                            mark_done(item)
            return out

        results: list[tuple[Any, Path, Path | None, str, bool, Any]] = []
        results.extend(run_batch(tasks))

        for variant, image_path, stl_path, key, delayed, result in results:
            entry = entries.get(variant.variant_id, {})
            if result.ok:
                entry["status"] = "ok"
                entry["key"] = key
                entry["image"] = image_path.name
                entry["stl"] = (
                    stl_path.name
                    if self.config.settings.mesh and stl_path and stl_path.is_file()
                    else None
                )
                entry["rendered_at"] = _now_iso()
                entry["duration_s"] = round(result.duration_s, 2)
                entry["error"] = None
                stats.rendered += 1
                LOG.info(
                    "[%s]   + %s  %.1fs",
                    rel,
                    variant.label,
                    result.duration_s,
                )
            else:
                entry["status"] = "error"
                entry["error"] = result.error or "unknown render error"
                entry["last_attempt"] = _now_iso()
                if result.log:
                    entry["log_tail"] = result.log[-3000:]
                if not entry.get("image"):
                    entry["image"] = None
                stats.failed += 1
                LOG.error(
                    "[%s]   ! %s: %s",
                    rel,
                    variant.label,
                    entry["error"],
                )

        # Record geometry size for the next run's biggest-first ordering.
        for group in groups:
            rep = group["rep"]
            entry = entries.get(rep.variant_id)
            if not entry:
                continue
            stl_name = entry.get("stl")
            if stl_name and (out_dir / str(stl_name)).is_file():
                stl_file = out_dir / str(stl_name)
                try:
                    entry["stl_bytes"] = stl_file.stat().st_size
                except OSError:
                    entry["stl_bytes"] = 0
                entry["triangles"] = _stl_triangles(stl_file)

        # Alias switch combinations that share exactly the same geometry.
        for group in groups:
            rep = group["rep"]
            rep_entry = entries[rep.variant_id]
            with_stl = bool(group["with_stl"])
            for alias in group["members"]:
                if alias is rep:
                    continue
                alias_entry: dict[str, Any] = {
                    "id": alias.variant_id,
                    "values": dict(alias.values),
                    "label": alias.label,
                    "stl_planned": with_stl,
                    "delayed": bool(group["delayed"]),
                    "geometry": group["sig"],
                    "alias_of": rep.variant_id,
                    "status": rep_entry.get("status", "pending"),
                    "image": rep_entry.get("image"),
                    "stl": rep_entry.get("stl") if with_stl else None,
                    "stl_bytes": rep_entry.get("stl_bytes") if with_stl else None,
                    "triangles": rep_entry.get("triangles") if with_stl else None,
                    "rendered_at": rep_entry.get("rendered_at"),
                    "duration_s": rep_entry.get("duration_s"),
                }
                if rep_entry.get("key"):
                    alias_entry["key"] = rep_entry.get("key")
                if rep_entry.get("error"):
                    alias_entry["error"] = rep_entry["error"]
                entries[alias.variant_id] = alias_entry

        # Remove outputs of variants that no longer exist.  Aliases share the
        # representative's files, so only representatives own files.
        expected_images = {f"{group['stem']}.png" for group in groups}
        expected_stls = {f"{stem}.stl" for stem in planned_stl_ids}
        # Remove stale final PNG/STL files from the flat output folder.
        for path in out_dir.iterdir():
            if not path.is_file():
                continue
            if path.suffix.lower() == ".png" and path.name not in expected_images:
                if path.name != "contact.png":
                    _safe_unlink(path, out_dir)
            elif path.suffix.lower() == ".stl" and path.name not in expected_stls:
                _safe_unlink(path, out_dir)

        ordered_variants: list[dict[str, Any]] = []
        for group in groups:
            rep = group["rep"]
            ordered_variants.append(entries[rep.variant_id])
            for member in group["members"]:
                if member is not rep:
                    ordered_variants.append(entries[member.variant_id])
        status = "ok"
        if stats.failed:
            status = "partial" if (stats.skipped or stats.rendered) else "error"
        if not variants:
            status = "error"

        manifest: dict[str, Any] = {
            "schema": 1,
            "app_version": APP_VERSION,
            "source": self._manifest_source(source),
            "source_sha256": scad.raw_sha256,
            "status": status,
            "error": None,
            "updated_at": _now_iso(),
            "stl_mode": self.config.stl_mode,
            "switches": [sw.signature() for sw in scad.switches],
            "dependencies": [str(p) for p in deps_all],
            "variants": ordered_variants,
        }
        if status != "ok":
            manifest["retry_after"] = (
                datetime.now().astimezone()
                + timedelta(seconds=self.config.retry_interval)
            ).isoformat(timespec="seconds")

        # Contact sheet (best-effort, requires Pillow).  Aliases share images,
        # so show each unique geometry once.
        contact_name = "contact.png"
        image_paths: list[Path] = []
        seen_images: set[str] = set()
        for v in ordered_variants:
            image = v.get("image")
            if not image or image in seen_images:
                continue
            seen_images.add(image)
            candidate = out_dir / str(image)
            if candidate.is_file():
                image_paths.append(candidate)
        if image_paths:
            if len(image_paths) < len(variants):
                contact_title = (
                    f"{Path(rel).stem} · {len(image_paths)} уник. "
                    f"из {len(variants)}"
                )
            else:
                contact_title = f"{Path(rel).stem} · {_variants_word(len(image_paths))}"
            ok = make_contact_sheet(
                image_paths,
                out_dir / contact_name,
                contact_title,
                self.config.settings,
            )
            if ok:
                manifest["contact"] = contact_name
        else:
            _safe_unlink(out_dir / contact_name, out_dir)

        _atomic_json(manifest_path, manifest)
        write_source_page(
            out_dir,
            manifest,
            contact_name if (out_dir / contact_name).is_file() else None,
        )
        _clean_tmp(out_dir)
        if progress is not None:
            progress.finish()
        # Store the fingerprint of the bytes that were actually analysed.
        # If the file changed during a long render, the next poll sees it.
        self.fingerprints[source] = self._fingerprint_from(
            scad.raw_sha256, dep_digests
        )
        elapsed = time.time() - started
        LOG.info(
            "[%s] %d variant(s): rendered %d, skipped %d, failed %d  (%.1fs)",
            rel,
            len(variants),
            stats.rendered,
            stats.skipped,
            stats.failed,
            elapsed,
        )
        if self.config.notify:
            notify_render(
                source=source,
                out_dir=out_dir,
                manifest=manifest,
                stats=stats,
                elapsed=elapsed,
            )
        index_path = out_dir / "index.html"
        if (
            self.config.auto_open_results
            and auto_open_results_enabled()
            and index_path.is_file()
        ):
            try:
                open_gallery_page(index_path)
            except Exception:
                LOG.exception("[%s] could not auto-open gallery", rel)
        return stats

    # -- cycle -------------------------------------------------------------

    def _source_complexity(self, source: Path) -> tuple[int, int, int, int]:
        """Largest known object first; heuristic fallback for new sources."""
        out_dir = self.source_dir(source)
        manifest = _load_json(out_dir / "manifest.json")
        triangles = 0
        stl_bytes = 0
        if manifest:
            for item in manifest.get("variants") or []:
                if not isinstance(item, dict):
                    continue
                triangles = max(triangles, int(item.get("triangles") or 0))
                stl_bytes = max(stl_bytes, int(item.get("stl_bytes") or 0))
                stl_name = item.get("stl")
                if stl_name and (out_dir / str(stl_name)).is_file():
                    stl_file = out_dir / str(stl_name)
                    triangles = max(triangles, _stl_triangles(stl_file))
                    try:
                        stl_bytes = max(stl_bytes, stl_file.stat().st_size)
                    except OSError:
                        pass
        if triangles or stl_bytes:
            return (triangles, stl_bytes, 0, 0)
        try:
            scad = analyze_scad(source)
            variants = build_variants(scad.switches, self.config.max_variants)
            rel = source.relative_to(self.root).as_posix()
            heavy = any(
                _stl_plan(rel, variant.values, self.config.stl_mode)[1]
                for variant in variants
            )
            return (0, 0, 1 if heavy else 0, len(variants))
        except Exception:
            return (0, 0, 0, 0)

    def _retry_due(self, source: Path) -> bool:
        path = self.source_dir(source) / "manifest.json"
        manifest = _load_json(path)
        if not manifest:
            return path.is_file()
        if manifest.get("status") == "ok":
            return False
        retry = manifest.get("retry_after")
        if not retry:
            return True
        try:
            due = datetime.fromisoformat(str(retry))
        except ValueError:
            return True
        return datetime.now().astimezone() >= due

    def run_cycle(self) -> CycleStats:
        sources = self.discover_sources()
        source_set = set(sources)
        removed = set(self.fingerprints) - source_set
        for old in removed:
            self.fingerprints.pop(old, None)
            self.dependency_map.pop(old, None)
            LOG.info("[%s] source removed", old.relative_to(self.root))

        queue: list[Path] = []
        if self._first_cycle:
            queue = list(sources)
        else:
            for source in sources:
                fp = self._fingerprint(source)
                if self.fingerprints.get(source) != fp:
                    queue.append(source)
            queued = set(queue)
            for source in sources:
                if source not in queued and self._retry_due(source):
                    queue.append(source)
        # Biggest known object first; heavy-value heuristic for new sources.
        queue.sort(key=self._source_complexity, reverse=True)

        stats = CycleStats(sources=len(sources))
        force = self._force_once
        for source in queue:
            if self._stop.is_set():
                break
            one = self.process_source(source, force=force)
            stats.rendered += one.rendered
            stats.skipped += one.skipped
            stats.failed += one.failed
            stats.errors += one.errors
        self._first_cycle = False
        self._force_once = False
        # Recompute fingerprints after the cycle, so edits made during a long
        # render are picked up on the next poll.
        for source in source_set:
            if source not in self.fingerprints:
                self.fingerprints[source] = self._fingerprint(source)
        return stats

    def run_once(self) -> CycleStats:
        self.lock.acquire()
        try:
            return self.run_cycle()
        finally:
            self.lock.release()

    def watch(self) -> None:
        self.lock.acquire()
        try:
            LOG.info("watching %s", self.root)
            LOG.info("state:  %s", self.state_root)
            while not self._stop.is_set():
                try:
                    stats = self.run_cycle()
                except Exception:
                    LOG.exception("cycle failed; will retry")
                    self._stop.wait(max(2.0, self.config.poll_interval))
                    continue
                if stats.rendered or stats.failed or stats.errors:
                    LOG.info(
                        "cycle: rendered %d, skipped %d, failed %d",
                        stats.rendered,
                        stats.skipped,
                        stats.failed,
                    )
                self._stop.wait(self.config.poll_interval)
        finally:
            self.lock.release()

    def stop(self) -> None:
        self._stop.set()
