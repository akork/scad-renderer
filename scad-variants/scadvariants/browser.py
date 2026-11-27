"""Open local SCAD pages in an isolated browser window.

The user's main browser profile (tabs, history, session) must not be touched.
We launch Edge/Chrome in app mode with a dedicated ``--user-data-dir``.  A
different user-data-dir always means a separate browser process/profile, so
this works even when Edge is also the default browser.
"""

from __future__ import annotations

import json
import logging
import subprocess
import webbrowser
from pathlib import Path

LOG = logging.getLogger(__name__)

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
SETTINGS_PATH = STATE_DIR / "ui-settings.json"
EDGE_CANDIDATES = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)
CHROME_CANDIDATES = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
)


def find_browser() -> Path | None:
    return next(
        (p for p in (*EDGE_CANDIDATES, *CHROME_CANDIDATES) if p.is_file()),
        None,
    )


def auto_open_results_enabled(default: bool = True) -> bool:
    """Read the shared tray checkbox without depending on the tray process."""
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default
    if not isinstance(data, dict):
        return default
    return bool(data.get("auto_open_results", default))


def open_in_isolated(
    target: str | Path,
    *,
    profile_name: str = "browser-profile",
    window_size: str = "1400,1000",
    app_mode: bool = True,
) -> bool:
    """Open a path or URL in an isolated browser window."""
    url = target.resolve().as_uri() if isinstance(target, Path) else str(target)
    profile = STATE_DIR / profile_name
    profile.mkdir(parents=True, exist_ok=True)

    browser = find_browser()
    if browser is None:
        LOG.warning("Edge/Chrome not found; falling back to default browser")
        return webbrowser.open(url, new=2)

    command = [
        str(browser),
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--disable-background-mode",
        f"--window-size={window_size}",
    ]
    if app_mode:
        command.append(f"--app={url}")
    else:
        command.append(url)
    try:
        subprocess.Popen(
            command,
            cwd=str(STATE_DIR),
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
        )
        LOG.info("opened isolated browser: %s -> %s", url, browser)
        return True
    except Exception as exc:
        LOG.warning("isolated browser failed: %s", exc)
        return webbrowser.open(url, new=2)
