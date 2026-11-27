#!/usr/bin/env python3
"""Render one .scad file in place from the Explorer context menu.

The ``scad-variants`` pipeline is invoked in one-shot mode with the selected
file's parent as ``--root`` and an exact-name ``--only`` filter.  Results are
written next to the source file; no folder is watched.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from ctypes import wintypes
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Sequence

APP_NAME = "scad-drop"


def _read_app_version() -> str:
    candidate = Path(__file__).resolve().parent.parent / "VERSION"
    try:
        value = candidate.read_text(encoding="utf-8").strip()
    except OSError:
        return "1.0.0"
    return value or "1.0.0"


APP_VERSION = _read_app_version()

DEFAULT_EXTENSIONS = (".scad",)
DEFAULT_POLL = 2.0
DEFAULT_STABLE = 2.0
DEFAULT_RENDER_TIMEOUT = 3600.0

PROJECT_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = PROJECT_DIR.parent
DEFAULT_SCAD_ROOT = WORKSPACE_DIR / "SCAD"
DEFAULT_TOOL = WORKSPACE_DIR / "scad-variants" / "scad_variants.py"
DEFAULT_RENDERER_STATE = WORKSPACE_DIR / "scad-variants" / "state"
DEFAULT_STATE = PROJECT_DIR / "state"
DEFAULT_DOWNLOADS = Path(
    os.environ.get("USERPROFILE") or str(Path.home())
) / "Downloads"

LOG = logging.getLogger(APP_NAME)

_MB_YESNO = 0x00000004
_MB_ICONQUESTION = 0x00000020
_MB_ICONERROR = 0x00000010
_MB_TOPMOST = 0x00040000
_MB_SETFOREGROUND = 0x00010000
_IDYES = 6


# ---------------------------------------------------------------------------
#  Small helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _norm(path: Path | str) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if value < 1024 or unit == "ГБ":
            if unit == "Б":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} ГБ"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    temp = path.parent / f".{path.name}.{uuid.uuid4().hex[:8]}.tmp"
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _setup_logging(state_root: Path, verbose: bool) -> None:
    state_root.mkdir(parents=True, exist_ok=True)
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    LOG.setLevel(logging.DEBUG if verbose else logging.INFO)
    LOG.handlers.clear()
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s", "%H:%M:%S")
    if sys.stdout is not None:
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        LOG.addHandler(console)
    file_handler = RotatingFileHandler(
        state_root / "scad_drop.log",
        maxBytes=2_000_000,
        backupCount=2,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    LOG.addHandler(file_handler)
    LOG.propagate = False


def _parse_extensions(value: str) -> tuple[str, ...]:
    out: list[str] = []
    for part in value.split(","):
        item = part.strip().lower()
        if not item:
            continue
        if not item.startswith("."):
            item = "." + item
        out.append(item)
    return tuple(out) or DEFAULT_EXTENSIONS


def _glob_exact(rel: str) -> str:
    """Escape a relative path so fnmatch matches it literally."""
    out: list[str] = []
    for char in rel:
        if char in "*?[":
            out.append("[" + char + "]")
        else:
            out.append(char)
    return "".join(out)


def _is_candidate(name: str, extensions: Sequence[str]) -> bool:
    lowered = name.lower()
    if lowered.startswith("~$"):
        return False
    if any(part in lowered for part in (".crdownload", ".part", ".tmp", ".download")):
        return False
    return any(lowered.endswith(ext) for ext in extensions)


# ---------------------------------------------------------------------------
#  State, lock and file stability
# ---------------------------------------------------------------------------


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        data = _load_json(self.path)
        if not data or not isinstance(data.get("files"), dict):
            data = {"version": 1, "files": {}}
        return data

    @property
    def files(self) -> dict[str, Any]:
        return self.data.setdefault("files", {})

    def get(self, key: str) -> dict[str, Any] | None:
        entry = self.files.get(key)
        return entry if isinstance(entry, dict) else None

    def put(self, key: str, entry: dict[str, Any]) -> None:
        with self._lock:
            self.files[key] = entry
            self.save()

    def save(self) -> None:
        with self._lock:
            _atomic_json(self.path, self.data)


class SingleInstance:
    """Cross-process lock so two prompt loops cannot run at once."""

    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.handle = self.path.open("a+b")
            self.handle.seek(0)
            try:
                empty = self.handle.read(1) == b""
            except PermissionError as exc:
                raise RuntimeError(
                    f"another scad-drop is already running ({self.path.parent})"
                ) from exc
            if empty:
                self.handle.write(b"0")
                self.handle.flush()
            self.handle.seek(0)
            if os.name == "nt":
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
                f"another scad-drop is already running ({self.path.parent})"
            ) from exc

    def release(self) -> None:
        if not self.handle:
            return
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self.handle.close()
        self.handle = None


class StabilityTracker:
    """Wait until a downloaded file stops changing before asking about it."""

    def __init__(self, seconds: float, clock=time.monotonic):
        self.seconds = max(0.0, seconds)
        self.clock = clock
        self._pending: dict[str, tuple[int, int, float]] = {}

    def ready(self, key: str, stat: os.stat_result) -> bool:
        now = self.clock()
        previous = self._pending.get(key)
        if (
            previous is not None
            and previous[0] == stat.st_size
            and previous[1] == stat.st_mtime_ns
        ):
            if self.seconds <= 0 or now - previous[2] >= self.seconds:
                return True
            return False
        self._pending[key] = (stat.st_size, stat.st_mtime_ns, now)
        return self.seconds <= 0


# ---------------------------------------------------------------------------
#  Discovery
# ---------------------------------------------------------------------------


def _stat_entry(path: Path) -> os.stat_result | None:
    try:
        return path.stat()
    except OSError:
        return None


def discover(
    downloads: Path,
    extensions: Sequence[str],
    recursive: bool = False,
) -> list[tuple[Path, os.stat_result]]:
    found: list[tuple[Path, os.stat_result]] = []
    if not downloads.is_dir():
        return found

    skip_dirs = {".git", ".hg", ".svn", "node_modules", "$RECYCLE.BIN"}

    if recursive:
        for dirpath, dirnames, filenames in os.walk(downloads, topdown=True):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            current = Path(dirpath)
            for name in filenames:
                if not _is_candidate(name, extensions):
                    continue
                path = current / name
                stat = _stat_entry(path)
                if stat is not None and path.is_file():
                    found.append((path, stat))
    else:
        try:
            entries = list(os.scandir(downloads))
        except OSError:
            return found
        for entry in entries:
            try:
                if not entry.is_file(follow_symlinks=False):
                    continue
            except OSError:
                continue
            if not _is_candidate(entry.name, extensions):
                continue
            path = Path(entry.path)
            stat = _stat_entry(path)
            if stat is not None:
                found.append((path, stat))

    found.sort(key=lambda item: (item[1].st_mtime_ns, item[0].name.lower()))
    return found


# ---------------------------------------------------------------------------
#  User interaction
# ---------------------------------------------------------------------------


def _message_box(text: str, title: str, flags: int) -> int:
    if os.name != "nt":
        return 0
    user32 = ctypes.windll.user32
    user32.MessageBoxW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_uint,
    ]
    user32.MessageBoxW.restype = ctypes.c_int
    return int(user32.MessageBoxW(None, text, title, flags))


def ask_render(source: Path, size: int) -> bool:
    if os.name != "nt":
        return True
    text = (
        "В папке Downloads появился новый файл:\n\n"
        f"{source.name}\n"
        f"{_human_size(size)}\n\n"
        "Отрендерить его и сгенерировать STL?"
    )
    flags = _MB_YESNO | _MB_ICONQUESTION | _MB_TOPMOST | _MB_SETFOREGROUND
    try:
        answer = _message_box(text, "SCAD — рендеринг", flags)
    except Exception:
        LOG.exception("could not show the confirmation dialog")
        return False
    return answer == _IDYES


def ask_open(source: Path) -> bool:
    if os.name != "nt":
        return True
    text = (
        "Открыть этот файл в OpenSCAD?\n\n"
        f"{source.name}\n\n"
        "Откроется новое окно OpenSCAD."
    )
    flags = _MB_YESNO | _MB_ICONQUESTION | _MB_TOPMOST | _MB_SETFOREGROUND
    try:
        answer = _message_box(text, "SCAD — открыть в OpenSCAD", flags)
    except Exception:
        LOG.exception("could not show the OpenSCAD dialog")
        return False
    return answer == _IDYES


class _ChoiceDialog:
    """One window: open in OpenSCAD? plus optional render checkbox."""

    def __init__(
        self,
        source: Path,
        size: int,
        openscad_available: bool,
        anchor_hwnd: int | None = None,
    ):
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.source = source
        self.openscad_available = openscad_available
        self.anchor_hwnd = anchor_hwnd
        self.result = (False, False)

        root = tk.Tk(className="SCADDrop")
        self.root = root
        root.title("SCAD — открыть?")
        root.resizable(False, False)
        root.minsize(460, 280)
        root.attributes("-topmost", True)
        root.withdraw()
        root.protocol("WM_DELETE_WINDOW", self._cancel)

        try:
            ttk.Style(root).theme_use("vista")
        except Exception:
            pass

        self.render_var = tk.BooleanVar(root, value=False)
        frame = ttk.Frame(root, padding=18)
        frame.grid(row=0, column=0, sticky="nsew")

        heading = (
            "Открыть этот файл в OpenSCAD?"
            if openscad_available
            else "OpenSCAD не найден"
        )
        ttk.Label(
            frame, text=heading, font=("Segoe UI", 13, "bold")
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            frame, text=source.name, font=("Segoe UI", 10, "bold")
        ).grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Label(
            frame, text=_human_size(size), foreground="#64748b"
        ).grid(row=2, column=0, sticky="w")

        if openscad_available:
            ttk.Label(
                frame,
                text="Откроется новое окно OpenSCAD.",
                foreground="#64748b",
            ).grid(row=3, column=0, sticky="w", pady=(6, 0))

        buttons = ttk.Frame(frame)
        buttons.grid(
            row=6 if openscad_available else 3,
            column=0,
            sticky="e",
            pady=(18, 0),
        )

        if openscad_available:
            self.check = ttk.Checkbutton(
                frame,
                text="Запустить рендеринг и генерацию STL",
                variable=self.render_var,
                takefocus=True,
            )
            self.check.grid(row=4, column=0, sticky="w", pady=(14, 2))
            ttk.Label(
                frame,
                text=(
                    "Галочка действует независимо от ответа: можно "
                    "отрендерить файл, не открывая его."
                ),
                foreground="#64748b",
                wraplength=430,
                justify="left",
            ).grid(row=5, column=0, sticky="w")

            ttk.Button(
                buttons,
                text="Не открывать",
                command=lambda: self._choose(False),
            ).grid(row=0, column=0, padx=(0, 8))
            open_button = ttk.Button(
                buttons,
                text="Открыть",
                command=lambda: self._choose(True),
            )
            open_button.grid(row=0, column=1)
            open_button.focus_set()
            self._default = lambda: self._choose(True)
        else:
            ttk.Button(
                buttons,
                text="Пропустить",
                command=lambda: self._choose(False, force_render=False),
            ).grid(row=0, column=0, padx=(0, 8))
            run_button = ttk.Button(
                buttons,
                text="Запустить рендеринг",
                command=lambda: self._choose(False, force_render=True),
            )
            run_button.grid(row=0, column=1)
            run_button.focus_set()
            self._default = lambda: self._choose(False, force_render=True)

        root.bind("<Return>", lambda _event: self._default())
        root.bind("<Escape>", lambda _event: self._cancel())

    def _choose(self, open_choice: bool, force_render: bool | None = None) -> None:
        render = (
            bool(self.render_var.get())
            if force_render is None
            else bool(force_render)
        )
        self.result = (bool(open_choice), render)
        self.root.destroy()

    def _cancel(self) -> None:
        self.result = (False, False)
        self.root.destroy()

    def _place(self) -> None:
        root = self.root
        width = max(460, root.winfo_reqwidth())
        height = max(280, root.winfo_reqheight())
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2

        if self.anchor_hwnd:
            user32 = ctypes.windll.user32
            user32.GetWindowRect.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(wintypes.RECT),
            ]
            rect = wintypes.RECT()
            if user32.GetWindowRect(self.anchor_hwnd, ctypes.byref(rect)):
                anchor_w = rect.right - rect.left
                anchor_h = rect.bottom - rect.top
                if anchor_w > 100 and anchor_h > 100:
                    x = rect.left + (anchor_w - width) // 2
                    y = rect.top + (anchor_h - height) // 2

        x = max(0, min(x, screen_w - width))
        y = max(0, min(y, screen_h - height))
        root.geometry(f"+{x}+{y}")

    def _activate(self) -> None:
        try:
            user32 = ctypes.windll.user32
            user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            user32.GetAncestor.restype = ctypes.c_void_p
            hwnd = int(self.root.winfo_id())
            top = int(user32.GetAncestor(hwnd, 2) or hwnd)  # GA_ROOT
            if not bring_window_to_front(top, allow_minimize=False):
                self.root.focus_force()
        except Exception:
            LOG.debug("could not activate the choice dialog", exc_info=True)

    def show(self) -> tuple[bool, bool]:
        self.root.update_idletasks()
        self.root.deiconify()
        self.root.update_idletasks()
        self._place()
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(100, self.root.focus_force)
        self.root.after(180, self._activate)
        self.root.mainloop()
        return self.result


def ask_choice(
    source: Path,
    size: int,
    openscad_available: bool,
    anchor_hwnd: int | None = None,
) -> tuple[bool, bool]:
    """Return (open_in_openscad, render_and_stl)."""
    if os.name != "nt":
        return (True, True)
    try:
        dialog = _ChoiceDialog(source, size, openscad_available, anchor_hwnd)
        return dialog.show()
    except Exception:
        LOG.exception("could not show the choice dialog; using native prompts")
        render = ask_render(source, size)
        open_ = ask_open(source) if openscad_available else False
        return (open_, render)


def find_openscad(explicit: str | None = None) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return path
        found = shutil.which(explicit)
        return Path(found) if found else None

    from_env = os.environ.get("OPENSCAD")
    if from_env:
        path = Path(from_env).expanduser()
        if path.is_file():
            return path

    tools = Path(__file__).resolve().parent.parent / "tools"
    if tools.is_dir():
        for candidate in sorted(
            tools.glob("openscad-*/openscad.exe"), reverse=True
        ):
            if candidate.is_file():
                return candidate

    for name in ("openscad.exe", "openscad"):
        found = shutil.which(name)
        if found:
            return Path(found)

    for base in (
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("LOCALAPPDATA"),
    ):
        if not base:
            continue
        for relative in ("OpenSCAD/openscad.exe", "Programs/OpenSCAD/openscad.exe"):
            candidate = Path(base) / relative
            if candidate.is_file():
                return candidate
    return None


def open_in_openscad(executable: Path, target: Path) -> bool:
    """Launch OpenSCAD for one file.  The GUI process is not waited for."""
    try:
        subprocess.Popen(
            [str(executable), str(target)],
            cwd=str(target.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        LOG.exception("could not open %s in OpenSCAD", target)
        return False
    LOG.info("opened in OpenSCAD: %s", target)
    return True


_EnumWindowsProc = ctypes.WINFUNCTYPE(
    ctypes.c_bool, ctypes.c_void_p, ctypes.c_ssize_t
)


def _window_title(hwnd: int) -> str:
    user32 = ctypes.windll.user32
    user32.GetWindowTextW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_int,
    ]
    buffer = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buffer, 512)
    return buffer.value


def _window_class(hwnd: int) -> str:
    user32 = ctypes.windll.user32
    user32.GetClassNameW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_int,
    ]
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, 256)
    return buffer.value


def _process_image_name(pid: int) -> str | None:
    """Full executable path for a PID; None when it cannot be queried."""
    if os.name != "nt" or pid <= 0:
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = [
        ctypes.c_ulong,
        ctypes.c_bool,
        ctypes.c_ulong,
    ]
    kernel32.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_wchar_p,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    kernel32.QueryFullProcessImageNameW.restype = ctypes.c_bool
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

    # PROCESS_QUERY_LIMITED_INFORMATION works for normal user processes,
    # including most elevated ones when they run as the same user.
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        size = ctypes.c_ulong(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(
            handle, 0, buffer, ctypes.byref(size)
        ):
            return buffer.value
        return None
    finally:
        kernel32.CloseHandle(handle)


def find_openscad_window() -> int | None:
    """Return the topmost visible OpenSCAD window, if the GUI is running.

    The window title is localized ("Добро пожаловать в OpenSCAD"), so the
    process executable is the primary signal; title/class is only a fallback
    when the process path cannot be queried.
    """
    if os.name != "nt":
        return None
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.GetWindowThreadProcessId.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
    user32.EnumWindows.argtypes = [_EnumWindowsProc, ctypes.c_ssize_t]
    user32.EnumWindows.restype = ctypes.c_bool

    found: list[int] = []

    def callback(hwnd, _lparam):
        try:
            handle = int(hwnd)
            if not user32.IsWindowVisible(handle):
                return True
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
            image = _process_image_name(pid.value)
            title = _window_title(handle)
            window_class = _window_class(handle)

            is_openscad = bool(
                image and Path(image).name.lower() == "openscad.exe"
            )
            if not is_openscad:
                # Fallback for processes whose image path is not readable.
                is_openscad = (
                    ("openscad" in title.lower() and window_class.startswith("Qt"))
                    or title.lower() == "openscad"
                    or title.lower().endswith(" - openscad")
                )
            if is_openscad:
                found.append(handle)
        except Exception:
            pass
        return True

    user32.EnumWindows(_EnumWindowsProc(callback), 0)
    if not found:
        return None

    foreground = int(user32.GetForegroundWindow() or 0)
    if foreground in found:
        return foreground
    return found[0]


def bring_window_to_front(hwnd: int, allow_minimize: bool = True) -> bool:
    """Focus an existing window; optionally fall back to minimize/restore."""
    if os.name != "nt" or not hwnd:
        return False
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.GetWindowThreadProcessId.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
    user32.AttachThreadInput.argtypes = [
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_bool,
    ]
    user32.AttachThreadInput.restype = ctypes.c_bool
    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    user32.BringWindowToTop.argtypes = [ctypes.c_void_p]
    user32.SetFocus.argtypes = [ctypes.c_void_p]
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.IsIconic.argtypes = [ctypes.c_void_p]

    if int(user32.GetForegroundWindow() or 0) == hwnd:
        return True

    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    else:
        user32.ShowWindow(hwnd, 5)  # SW_SHOW

    foreground = int(user32.GetForegroundWindow() or 0)
    foreground_tid = (
        user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    )
    target_tid = user32.GetWindowThreadProcessId(hwnd, None)
    attached = False
    if foreground_tid and target_tid and foreground_tid != target_tid:
        attached = bool(
            user32.AttachThreadInput(foreground_tid, target_tid, True)
        )
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(foreground_tid, target_tid, False)

    time.sleep(0.2)
    if int(user32.GetForegroundWindow() or 0) == hwnd:
        return True

    if not allow_minimize:
        # Never minimize the dialog itself: Tk does not repaint its widgets
        # after a minimize/restore cycle, leaving a black client area.
        return False

    # Windows can refuse SetForegroundWindow.  A minimize/restore cycle is
    # the reliable fallback (it keeps a maximized window maximized).
    user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
    time.sleep(0.35)
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    time.sleep(0.45)
    return int(user32.GetForegroundWindow() or 0) == hwnd


def show_error(text: str) -> None:
    if os.name != "nt":
        LOG.error("%s", text)
        return
    text = text.strip()
    if len(text) > 900:
        text = text[:900] + "..."
    flags = _MB_ICONERROR | _MB_TOPMOST | _MB_SETFOREGROUND
    try:
        _message_box(text, "SCAD — ошибка", flags)
    except Exception:
        LOG.exception("could not show the error dialog")


# ---------------------------------------------------------------------------
#  Copy and render
# ---------------------------------------------------------------------------


def copy_into_scad(source: Path, scad_root: Path) -> tuple[Path, bool]:
    """Copy the download into SCAD; never overwrite a different file.

    Returns ``(target, copied)``.  An identical file is reused as is.  A
    different file with the same name gets a ``__2``/``__3`` suffix, so an
    older render is never destroyed.
    """
    scad_root.mkdir(parents=True, exist_ok=True)
    target = scad_root / source.name
    if target.exists():
        try:
            if _sha256(target) == _sha256(source):
                return target, False
        except OSError:
            pass
        stem, suffix = target.stem, target.suffix
        number = 2
        while True:
            candidate = scad_root / f"{stem}__{number}{suffix}"
            if not candidate.exists():
                target = candidate
                break
            number += 1
    shutil.copy2(source, target)
    return target, True


def gallery_dir(target: Path) -> Path:
    return target.parent / f"{target.stem}_renders"


def renderer_running(lock_path: Path) -> bool:
    """Return True when the SCAD watcher holds its byte-range lock.

    The lock also blocks reads of the locked byte, so reading the PID is not
    reliable.  Trying to take the lock ourselves is the reliable probe.
    """
    if not lock_path.is_file():
        return False
    try:
        if lock_path.stat().st_size == 0:
            return False
    except OSError:
        return False

    handle = None
    try:
        handle = lock_path.open("r+b")
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                return True
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            return False
        import fcntl

        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return False
    except OSError:
        # Could not open it: another process is probably holding it.
        return True
    finally:
        if handle is not None:
            handle.close()


def run_one_shot(
    tool: Path,
    scad_root: Path,
    renderer_state: Path,
    relative: str,
    timeout: float,
) -> tuple[bool, str]:
    """Render exactly one file, respecting the watcher's lock."""
    pattern = _glob_exact(relative)
    command = [
        sys.executable,
        "-u",
        str(tool),
        "--once",
        "--root",
        str(scad_root),
        "--state",
        str(renderer_state),
        "--only",
        pattern,
        "--no-auto-open",
    ]
    LOG.info("one-shot render: %s", relative)
    try:
        proc = subprocess.run(
            command,
            cwd=str(tool.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        LOG.error("one-shot render timed out after %.0fs", timeout)
        pid = getattr(exc, "pid", None)
        if pid:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        return False, f"timeout after {timeout:.0f}s"

    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if proc.returncode == 0:
        return True, output
    if proc.returncode == 2 and "another watcher" in output.lower():
        return False, "locked"
    return False, (output[-4000:] or f"exit code {proc.returncode}")


def wait_for_gallery(
    target: Path,
    timeout: float,
    poll: float,
) -> Path | None:
    index = gallery_dir(target) / "index.html"
    deadline = time.monotonic() + max(1.0, timeout)
    while time.monotonic() < deadline:
        if index.is_file():
            return index
        time.sleep(max(0.25, poll))
    return None


def open_gallery(index: Path) -> None:
    try:
        variants_dir = str(WORKSPACE_DIR / "scad-variants")
        if variants_dir not in sys.path:
            sys.path.insert(0, variants_dir)
        from scadvariants.browser import auto_open_results_enabled
        from scadvariants.gallery_server import open_gallery_page

        if not auto_open_results_enabled():
            LOG.info("result auto-open is disabled")
            return
        if open_gallery_page(index):
            return
    except Exception:
        LOG.exception("isolated gallery open failed for %s", index)
    try:
        if os.name == "nt":
            os.startfile(str(index))
        else:
            subprocess.Popen(["xdg-open", str(index)])
    except Exception:
        LOG.exception("could not open %s", index)


# ---------------------------------------------------------------------------
#  One candidate
# ---------------------------------------------------------------------------


def _entry(stat: os.stat_result, status: str, **extra: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "status": status,
        "decided_at": _now_iso(),
    }
    data.update(extra)
    return data


def handle_candidate(
    source: Path,
    args: argparse.Namespace,
    state: StateStore,
) -> None:
    try:
        stat = source.stat()
    except OSError:
        return
    key = _norm(source)

    if args.dry_run:
        LOG.info("[dry-run] would ask about %s", source.name)
        state.put(key, _entry(stat, "ignored", note="dry-run"))
        return

    want_render = False
    want_open = False
    anchor_hwnd = None

    if args.no_popup or args.yes or args.yes_open:
        want_render = bool(args.yes)
        want_open = bool(args.yes_open and args.openscad_exe)
        LOG.info(
            "auto choice: open=%s render=%s (%s)",
            want_open,
            want_render,
            source.name,
        )
    else:
        anchor_hwnd = find_openscad_window()
        if anchor_hwnd:
            LOG.info("focusing existing OpenSCAD window (hwnd=%s)", anchor_hwnd)
            if bring_window_to_front(anchor_hwnd):
                LOG.info("OpenSCAD window is in front")
            else:
                LOG.warning("could not focus the OpenSCAD window")
            time.sleep(0.35)
        else:
            LOG.info("no existing OpenSCAD window")

        want_open, want_render = ask_choice(
            source,
            stat.st_size,
            bool(args.openscad_exe),
            anchor_hwnd,
        )
        LOG.info(
            "choice: open=%s render=%s (%s)",
            want_open,
            want_render,
            source.name,
        )

    if not want_render and not want_open:
        LOG.info("declined: %s", source.name)
        entry = _entry(stat, "declined")
        if args.no_popup:
            entry["note"] = "no-popup"
        state.put(key, entry)
        return

    if want_render:
        try:
            target, copied = copy_into_scad(source, args.scad_root)
        except Exception as exc:
            LOG.exception("could not copy %s", source)
            state.put(key, _entry(stat, "error", error=str(exc)))
            if not args.no_popup:
                show_error(
                    f"Не удалось скопировать файл в SCAD:\n\n{source.name}\n\n{exc}"
                )
            return
        LOG.info(
            "%s: %s -> %s",
            "copied" if copied else "already in SCAD",
            source.name,
            target,
        )
    else:
        # No render means no copy: open the original download, so the SCAD
        # watcher does not render it behind the user's back.
        target = source
        LOG.info("render declined; OpenSCAD will open the original: %s", source)

    state.put(
        key,
        _entry(
            stat,
            "accepted",
            target=str(target),
            render=want_render,
            open_openscad=want_open,
        ),
    )

    if want_open and args.openscad_exe:
        if not open_in_openscad(args.openscad_exe, target):
            message = (
                "Файл скопирован в SCAD, но запустить OpenSCAD не удалось.\n\n"
                f"{target}\n\n"
                "Проверь, что openscad.exe доступен, или укажи --openscad PATH."
            )
            LOG.error("OpenSCAD launch failed for %s", target)
            state.put(
                key,
                _entry(
                    stat,
                    "error",
                    target=str(target),
                    error="OpenSCAD launch failed",
                    render=want_render,
                ),
            )
            if not args.no_popup:
                show_error(message)
            if not want_render:
                return

    if not want_render:
        LOG.info("render skipped: %s", target)
        return

    relative = target.relative_to(args.scad_root).as_posix()
    watcher_running = renderer_running(args.renderer_state / ".watch.lock")
    if watcher_running:
        LOG.info("SCAD watcher is running; it will render the file")
    else:
        ok, detail = run_one_shot(
            args.tool,
            args.scad_root,
            args.renderer_state,
            relative,
            args.render_timeout,
        )
        if not ok and detail != "locked":
            LOG.error("render failed for %s: %s", target, detail)
            state.put(
                key,
                _entry(stat, "error", target=str(target), error=detail[-2000:]),
            )
            if not args.no_popup:
                show_error(
                    "Файл скопирован в SCAD, но рендер завершился ошибкой:\n\n"
                    f"{target.name}\n\n{detail[-700:]}"
                )
            return
        if detail == "locked":
            LOG.info("renderer lock is busy; waiting for the running watcher")

    index = wait_for_gallery(target, args.render_timeout, args.poll)
    if index is None:
        message = (
            "Файл скопирован в SCAD, но каталог рендера так и не появился.\n\n"
            f"{target}\n\n"
            "Проверь, что наблюдатель SCAD запущен, и посмотри лог."
        )
        LOG.error("gallery timeout for %s", target)
        state.put(
            key,
            _entry(stat, "error", target=str(target), error="gallery timeout"),
        )
        if not args.no_popup:
            show_error(message)
        return

    LOG.info("gallery ready: %s", index)
    if args.open and not watcher_running:
        open_gallery(index)


# ---------------------------------------------------------------------------
#  Main loop
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Render one .scad file in place (Explorer context-menu mode)."
        )
    )
    parser.add_argument(
        "--tool",
        default=str(DEFAULT_TOOL),
        help="path to scad_variants.py",
    )
    parser.add_argument(
        "--renderer-state",
        default=str(DEFAULT_RENDERER_STATE),
        help="state folder for temporary render state",
    )
    parser.add_argument(
        "--state",
        default=str(DEFAULT_STATE),
        help="state folder for this helper (default: <project>/state)",
    )
    parser.add_argument(
        "--render-file",
        metavar="PATH",
        required=True,
        help="render one .scad file in place and exit",
    )
    parser.add_argument(
        "--render-timeout",
        type=float,
        default=DEFAULT_RENDER_TIMEOUT,
        help="seconds to wait for a render/gallery",
    )
    parser.add_argument(
        "--no-open",
        "--no-gallery",
        dest="open",
        action="store_false",
        default=True,
        help="do not open the HTML gallery after rendering",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


def render_one_file(
    source: Path,
    tool: Path,
    renderer_state: Path,
    timeout: float,
    open_result: bool = True,
) -> int:
    """Render one .scad file in place (Explorer context-menu mode)."""
    source = Path(source).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".scad":
        message = f"Это не файл .scad:\n{source}"
        LOG.error("%s", message)
        show_error(message)
        return 2
    if not tool.is_file():
        message = f"Не найден scad_variants.py:\n{tool}"
        LOG.error("%s", message)
        show_error(message)
        return 2

    # A private state folder avoids the main SCAD watcher's lock and does not
    # pollute a Downloads folder with a state directory.
    temp_state = renderer_state / f"context-{uuid.uuid4().hex[:8]}"
    temp_state.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-u",
        str(tool),
        "--once",
        "--root",
        str(source.parent),
        "--state",
        str(temp_state),
        "--only",
        _glob_exact(source.name),
        "--force",
        "--no-auto-open",
    ]
    LOG.info("context render: %s", source)
    try:
        returncode = subprocess.call(command, cwd=str(tool.parent))
    except Exception as exc:
        LOG.exception("could not start context render for %s", source)
        shutil.rmtree(temp_state, ignore_errors=True)
        show_error(f"Не удалось запустить рендеринг:\n\n{source}\n\n{exc}")
        return 1

    if returncode != 0:
        shutil.rmtree(temp_state, ignore_errors=True)
        message = (
            "Рендеринг завершился ошибкой.\n\n"
            f"{source}\n\n"
            "Подробности — в окне консоли и в scad_drop.log."
        )
        LOG.error("context render failed for %s (exit %s)", source, returncode)
        show_error(message)
        return returncode

    index = wait_for_gallery(source, timeout, 2.0)
    shutil.rmtree(temp_state, ignore_errors=True)
    if index is None:
        message = (
            "Рендеринг завершился, но каталог _renders не появился.\n\n"
            f"{source}"
        )
        LOG.error("context gallery timeout: %s", source)
        show_error(message)
        return 1

    LOG.info("context gallery ready: %s", index)
    if open_result:
        open_gallery(index)
    return 0


def main(argv: list[str] | None = None) -> int:
    # pythonw.exe has no console: sys.stdout/sys.stderr are None.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    args = _build_parser().parse_args(argv)
    args.tool = Path(args.tool).expanduser().resolve()
    args.renderer_state = Path(args.renderer_state).expanduser().resolve()
    args.state = Path(args.state).expanduser().resolve()

    _setup_logging(args.state, args.verbose)
    return render_one_file(
        Path(args.render_file),
        args.tool,
        args.renderer_state,
        args.render_timeout,
        open_result=args.open,
    )


if __name__ == "__main__":
    raise SystemExit(main())
