#!/usr/bin/env python3
"""Focus the running OrcaSlicer window or launch it if needed."""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
import urllib.parse
from ctypes import wintypes
from logging.handlers import RotatingFileHandler
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
STATE_DIR = PROJECT_DIR / "state"
LOG_PATH = STATE_DIR / "slicer.log"
ORCA_CANDIDATES = (
    Path(r"C:\Program Files\OrcaSlicer\orca-slicer.exe"),
    Path(r"C:\Program Files\Snapmaker_Orca\snapmaker-orca.exe"),
)
LOG = logging.getLogger("scad-slicer")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetForegroundWindow.restype = wintypes.HWND
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.SetFocus.argtypes = [wintypes.HWND]
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SW_RESTORE = 9


def setup_logging() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG.setLevel(logging.INFO)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=500_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s"))
    LOG.addHandler(handler)
    LOG.propagate = False


def process_exe(pid: int) -> str:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def window_title(hwnd: wintypes.HWND) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def find_orca_windows() -> list[tuple[wintypes.HWND, int, str, str]]:
    found: list[tuple[wintypes.HWND, int, str, str]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        exe = os.path.basename(process_exe(pid.value)).lower()
        if exe not in {"orca-slicer.exe", "snapmaker-orca.exe"}:
            return True
        found.append((hwnd, pid.value, exe, window_title(hwnd)))
        return True

    user32.EnumWindows(callback, 0)
    # Prefer the official OrcaSlicer over the older Snapmaker build.
    found.sort(key=lambda item: (item[2] != "orca-slicer.exe", item[3] == ""))
    return found


def focus_window(hwnd: wintypes.HWND) -> None:
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.AllowSetForegroundWindow(0xFFFFFFFF)
    foreground = user32.GetForegroundWindow()
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    current_thread = kernel32.GetCurrentThreadId()
    fg_thread = 0
    if foreground:
        fg_thread = user32.GetWindowThreadProcessId(foreground, None)
    attached = False
    try:
        if fg_thread and fg_thread != target_thread:
            attached = bool(user32.AttachThreadInput(fg_thread, target_thread, True))
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(fg_thread, target_thread, False)


def show_error(message: str) -> None:
    LOG.error("%s", message)
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.user32.MessageBoxW(None, message, "SCAD slicer", 0x10)
    except Exception:
        pass


def open_orca() -> int:
    windows = find_orca_windows()
    if windows:
        hwnd, pid, exe, title = windows[0]
        LOG.info("focus Orca window: pid=%s exe=%s title=%s", pid, exe, title)
        focus_window(hwnd)
        return 0
    exe = next((p for p in ORCA_CANDIDATES if p.is_file()), None)
    if exe is None:
        show_error("OrcaSlicer не найден.")
        return 1
    LOG.info("launch Orca: %s", exe)
    try:
        subprocess.Popen(
            [str(exe)],
            cwd=str(exe.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return 0
    except Exception as exc:
        show_error(f"Не удалось запустить OrcaSlicer:\n\n{exc}")
        return 1


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        show_error("Usage: slicer_action.py scad-slicer://open?name=orca")
        return 2
    parsed = urllib.parse.urlsplit(args[0])
    if parsed.scheme.lower() != "scad-slicer":
        show_error(f"Unsupported URI: {args[0]}")
        return 2
    query = urllib.parse.parse_qs(parsed.query)
    name = (query.get("name") or ["orca"])[0].lower()
    if name != "orca":
        show_error("Этот слайсер пока не подключён.")
        return 2
    return open_orca()


if __name__ == "__main__":
    raise SystemExit(main())
