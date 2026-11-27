#!/usr/bin/env python3
"""Dedicated Edge preview browser with tab reuse.

The render preview lives in its own Edge profile with a local DevTools
endpoint.  If the requested render is already open, its tab is activated and
the Edge window is brought to the foreground.  Otherwise a new tab is opened.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import subprocess
import time
import urllib.parse
import urllib.request
from ctypes import wintypes
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .browser import find_browser

PROJECT_DIR = Path(__file__).resolve().parent.parent
STATE_DIR = PROJECT_DIR / "state"
STATE_PATH = STATE_DIR / "edge-preview.json"
LOG_PATH = STATE_DIR / "edge-preview.log"
PROFILE_DIR = STATE_DIR / "edge-preview-profile"
PORT = 9222
LOG = logging.getLogger("edge-preview")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.EnumWindows.argtypes = [
    ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
    wintypes.LPARAM,
]
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
user32.SwitchToThisWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t]
user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_uint,
]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.SystemParametersInfoW.argtypes = [
    wintypes.UINT,
    wintypes.UINT,
    ctypes.c_void_p,
    wintypes.UINT,
]
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

SW_RESTORE = 9
HWND_TOP = 0
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_SHOWWINDOW = 0x0040
SPI_SETFOREGROUNDLOCKTIMEOUT = 0x2001
SPIF_SENDCHANGE = 0x0002


def setup_logging() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG.setLevel(logging.INFO)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=500_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s"))
    LOG.addHandler(handler)
    LOG.propagate = False


def read_state() -> dict:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_state(data: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def http_json(url: str, method: str = "GET", timeout: float = 2.0):
    request = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8")) if raw else {}


def health() -> bool:
    try:
        data = http_json(f"http://127.0.0.1:{PORT}/json/version")
        return isinstance(data, dict) and bool(data.get("webSocketDebuggerUrl"))
    except Exception:
        return False


def launch_browser(url: str = "about:blank") -> None:
    browser = find_browser()
    if browser is None:
        raise RuntimeError("Edge not found")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    command = [
        str(browser),
        f"--user-data-dir={PROFILE_DIR}",
        f"--remote-debugging-port={PORT}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--disable-background-mode",
        "--window-size=1400,1000",
        "--new-window",
        url,
    ]
    proc = subprocess.Popen(
        command,
        cwd=str(STATE_DIR),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
    )
    write_state({"pid": int(proc.pid), "port": PORT, "profile": str(PROFILE_DIR)})
    LOG.info("launch Edge pid=%s port=%s", proc.pid, PORT)


def visible_edge_windows() -> list[tuple[wintypes.HWND, int, str]]:
    result: list[tuple[wintypes.HWND, int, str]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = window_title(hwnd)
        if "microsoft" not in title.lower() or "edge" not in title.lower():
            return True
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        result.append((hwnd, owner.value, title))
        return True

    user32.EnumWindows(callback, 0)
    return result


def ensure_browser() -> None:
    state = read_state()
    if int(state.get("port") or 0) == PORT and health():
        return
    before = {hwnd for hwnd, _pid, _title in visible_edge_windows()}
    launch_browser()
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if health():
            break
        time.sleep(0.25)
    else:
        raise RuntimeError("Edge DevTools endpoint did not start")
    # The launcher process can hand off to the real browser process; remember
    # the process that actually owns the new top-level Edge window.
    for _ in range(10):
        new_windows = [
            item for item in visible_edge_windows() if item[0] not in before
        ]
        if new_windows:
            hwnd, pid, title = max(new_windows, key=lambda item: len(item[2]))
            state = read_state()
            state.update({"pid": int(pid), "port": PORT, "profile": str(PROFILE_DIR)})
            write_state(state)
            LOG.info("adopted Edge window pid=%s title=%s", pid, title)
            break
        time.sleep(0.2)


def list_tabs() -> list[dict]:
    try:
        data = http_json(f"http://127.0.0.1:{PORT}/json/list")
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict) and item.get("type") == "page"]


def decode_folder(token: str) -> Path | None:
    try:
        from .gallery_server import decode_folder as decode

        return decode(token)
    except Exception:
        return None


def same_render(target: str, index: Path) -> bool:
    if not target:
        return False
    parsed = urllib.parse.urlsplit(target)
    path_text = urllib.parse.unquote(parsed.path)
    if parsed.scheme == "file":
        # file:///C:/... gives a leading slash before the drive letter.
        if len(path_text) >= 3 and path_text[0] == "/" and path_text[2] == ":":
            path_text = path_text[1:]
        try:
            return Path(path_text).resolve() == index.resolve()
        except (OSError, ValueError):
            return False
    if parsed.scheme in {"http", "https"} and "/r/" in parsed.path:
        try:
            token = parsed.path.split("/r/", 1)[1].split("/", 1)[0]
        except IndexError:
            return False
        folder = decode_folder(token)
        if folder is not None:
            try:
                return (folder / "index.html").resolve() == index.resolve()
            except OSError:
                return False
    return False


def window_title(hwnd: wintypes.HWND) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def focus_window(pid: int, hint: str) -> None:
    candidates: list[tuple[int, int, int, str, wintypes.HWND]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        title = window_title(hwnd)
        if not title:
            return True
        if owner.value == pid or (hint and hint.lower() in title.lower()):
            rect = wintypes.RECT()
            area = 0
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                area = max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
            candidates.append(
                (
                    0 if owner.value == pid else 1,
                    0 if hint and hint.lower() in title.lower() else 1,
                    -area,
                    title,
                    hwnd,
                )
            )
        return True

    user32.EnumWindows(callback, 0)
    if not candidates:
        LOG.warning("Edge window not found (pid=%s hint=%s)", pid, hint)
        return
    candidates.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    hwnd = candidates[0][4]
    LOG.info("focus Edge window: %s", candidates[0][3])

    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetWindowPos(hwnd, HWND_TOP, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW)
    user32.AllowSetForegroundWindow(0xFFFFFFFF)
    foreground = user32.GetForegroundWindow()
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    fg_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    attached = False
    try:
        if fg_thread and fg_thread != target_thread:
            attached = bool(user32.AttachThreadInput(fg_thread, target_thread, True))
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
        user32.SwitchToThisWindow(hwnd, True)
        # A synthetic Alt tap lifts Windows' foreground lock without visibly
        # opening the menu on the target window.
        user32.keybd_event(0x12, 0, 0, 0)
        user32.keybd_event(0x12, 0, 2, 0)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(fg_thread, target_thread, False)


def activate_tab(target_id: str) -> None:
    try:
        urllib.request.urlopen(
            f"http://127.0.0.1:{PORT}/json/activate/{urllib.parse.quote(target_id)}",
            timeout=3,
        ).read()
    except Exception:
        LOG.exception("activate target failed")


def close_tab(target_id: str) -> None:
    try:
        urllib.request.urlopen(
            f"http://127.0.0.1:{PORT}/json/close/{urllib.parse.quote(target_id)}",
            timeout=3,
        ).read()
    except Exception:
        pass


def open_tab(url: str) -> str:
    quoted = urllib.parse.quote(url, safe="")
    for method in ("PUT", "GET"):
        try:
            data = http_json(f"http://127.0.0.1:{PORT}/json/new?{quoted}", method=method)
            return str(data.get("id") or "")
        except Exception:
            continue
    # Last resort: attach a new tab through the browser's command line.
    browser = find_browser()
    if browser is not None:
        subprocess.Popen(
            [
                str(browser),
                f"--user-data-dir={PROFILE_DIR}",
                f"--remote-debugging-port={PORT}",
                "--no-first-run",
                "--no-default-browser-check",
                url,
            ],
            cwd=str(STATE_DIR),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
        )
    return ""


def open_render(index: Path) -> int:
    setup_logging()
    index = index.resolve()
    if not index.is_file():
        LOG.error("render index not found: %s", index)
        return 1
    ensure_browser()
    url = index.as_uri()
    tabs = list_tabs()
    existing = next((tab for tab in tabs if same_render(str(tab.get("url") or ""), index)), None)
    if existing:
        target_id = str(existing.get("id") or "")
        title = str(existing.get("title") or "")
        LOG.info("reuse tab: %s (%s)", target_id, title)
        if target_id:
            activate_tab(target_id)
    else:
        LOG.info("new tab: %s", url)
        target_id = open_tab(url)
        if target_id:
            activate_tab(target_id)
        for tab in list_tabs():
            tab_url = str(tab.get("url") or "")
            tab_id = str(tab.get("id") or "")
            if tab_id and tab_id != target_id and tab_url in {"about:blank", "edge://newtab/"}:
                close_tab(tab_id)
    state = read_state()
    pid = int(state.get("pid") or 0)
    focus_window(pid, index.parent.name.removesuffix("_renders"))
    return 0


def main(argv: list[str] | None = None) -> int:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        return 2
    return open_render(Path(args[0]))


if __name__ == "__main__":
    raise SystemExit(main())
