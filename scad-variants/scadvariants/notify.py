from __future__ import annotations

import ctypes
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .paths import resource_root

LOG = logging.getLogger("scadvariants")

APP_USER_MODEL_ID = "ScadDrop.Render"
TOAST_SCRIPT = resource_root() / "scadvariants" / "show-toast.ps1"
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _stl_count(out_dir: Path, manifest: dict[str, Any]) -> int:
    seen: set[str] = set()
    for variant in manifest.get("variants") or []:
        stl = variant.get("stl")
        if stl and (out_dir / str(stl)).is_file():
            seen.add(str(stl))
    return len(seen)


def _notifications_accepting() -> bool | None:
    if os.name != "nt":
        return None
    try:
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        shell32.SHQueryUserNotificationState.argtypes = [
            ctypes.POINTER(ctypes.c_int)
        ]
        shell32.SHQueryUserNotificationState.restype = ctypes.c_long
        state = ctypes.c_int()
        result = shell32.SHQueryUserNotificationState(ctypes.byref(state))
        if result != 0:
            return None
        # 5 = QUNS_ACCEPTS_NOTIFICATIONS, 7 = QUNS_APP
        return state.value in (5, 7)
    except Exception:
        return None


def _is_low_integrity() -> bool:
    """True for DSH-sandboxed low-integrity processes (no toast identity)."""
    if os.name != "nt":
        return False
    token = ctypes.c_void_p()
    try:
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.OpenProcessToken.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        if not kernel32.OpenProcessToken(
            kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)
        ):
            return False

        advapi32.GetTokenInformation.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong),
        ]
        size = ctypes.c_ulong(0)
        advapi32.GetTokenInformation(
            token, 25, None, 0, ctypes.byref(size)
        )
        if size.value == 0:
            return False
        buffer = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(
            token, 25, buffer, size, ctypes.byref(size)
        ):
            return False

        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
        advapi32.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
        advapi32.GetSidSubAuthorityCount.restype = ctypes.POINTER(
            ctypes.c_ubyte
        )
        advapi32.GetSidSubAuthority.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
        ]
        advapi32.GetSidSubAuthority.restype = ctypes.POINTER(ctypes.c_ulong)
        count = advapi32.GetSidSubAuthorityCount(sid).contents.value
        if count == 0:
            return False
        rid = advapi32.GetSidSubAuthority(sid, count - 1).contents.value
        return rid < 0x2000  # SECURITY_MANDATORY_MEDIUM_RID
    except Exception:
        return False
    finally:
        if token:
            try:
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
                kernel32.CloseHandle(token)
            except Exception:
                pass


def notify_render(
    source: Path,
    out_dir: Path,
    manifest: dict[str, Any],
    stats: Any,
    elapsed: float,
    enabled: bool = True,
) -> None:
    """Show a Windows toast with a one-file render summary."""
    if not enabled or os.name != "nt":
        return
    rendered = int(getattr(stats, "rendered", 0))
    failed = int(getattr(stats, "failed", 0))
    errors = int(getattr(stats, "errors", 0))
    if rendered == 0 and failed == 0 and errors == 0:
        return
    if not TOAST_SCRIPT.is_file():
        LOG.debug("toast script not found: %s", TOAST_SCRIPT)
        return

    if _is_low_integrity():
        LOG.info(
            "toast skipped: DSH sandbox has no Windows notification identity "
            "(use the SCAD Render shortcut for notifications)"
        )
        return
    if _notifications_accepting() is False:
        LOG.warning(
            "toast skipped: Windows notifications are suppressed "
            "(Focus Assist / Do Not Disturb or busy mode)"
        )
        return

    powershell = shutil.which("powershell.exe")
    if not powershell:
        return

    variants = len(manifest.get("variants") or [])
    stl_count = _stl_count(out_dir, manifest)
    parts = [f"PNG: {rendered}"]
    if stl_count:
        parts.append(f"STL: {stl_count}")
    parts.append(f"вариантов: {variants}")
    problems = failed + errors
    if problems:
        parts.append(f"ошибок: {problems}")
    parts.append(f"{elapsed:.1f} с")

    title = f"SCAD: {source.stem}"
    body = f"{source.name}\n" + " · ".join(parts)
    launch = ""
    index = out_dir / "index.html"
    if index.is_file():
        launch = (
            "scad-gallery://open?path="
            + quote(str(index.resolve()), safe="")
        )
    elif out_dir.is_dir():
        launch = out_dir.as_uri().rstrip("/") + "/"

    command = [
        powershell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(TOAST_SCRIPT),
        "-Title",
        title,
        "-Body",
        body,
        "-Aumid",
        APP_USER_MODEL_ID,
    ]
    if launch:
        command += ["-Launch", launch]

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
            creationflags=_CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            LOG.info("toast shown: %s", source.name)
        else:
            LOG.warning(
                "toast helper exited %s for %s",
                result.returncode,
                source.name,
            )
    except subprocess.TimeoutExpired:
        LOG.warning("toast helper timed out for %s", source.name)
    except Exception:
        LOG.debug("could not send toast for %s", source.name, exc_info=True)
