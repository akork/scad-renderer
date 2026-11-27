#!/usr/bin/env python3
"""Lazy local 3D viewer for scad-variants galleries.

The gallery links to a custom ``scad-viewer:`` URI.  Windows launches this
script (through the per-user protocol registration), which validates the
requested folder, starts a loopback-only HTTP server and opens the viewer.
The server exits after a period without requests.
"""

from __future__ import annotations

import logging
import json
import os
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from pathlib import Path

from scadvariants.browser import open_in_isolated

PROJECT_DIR = Path(__file__).resolve().parent
VIEWER_DIR = PROJECT_DIR / "viewer"
VIEWER_HTML = VIEWER_DIR / "viewer.html"
VENDOR_DIR = VIEWER_DIR / "vendor"
STATE_DIR = PROJECT_DIR / "state"
LOG_PATH = STATE_DIR / "viewer.log"
IDLE_SECONDS = 30 * 60
VENDOR_FILES = {
    "three.min.js": "application/javascript; charset=utf-8",
    "STLLoader.js": "application/javascript; charset=utf-8",
    "OrbitControls.js": "application/javascript; charset=utf-8",
}


def open_viewer_browser(url: str) -> bool:
    return open_in_isolated(url, profile_name="browser-profile")

LOG = logging.getLogger("scad-viewer")


def setup_logging() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        LOG_PATH, maxBytes=1_000_000, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s")
    )
    LOG.addHandler(handler)
    LOG.propagate = False


def allowed_roots() -> list[Path]:
    return [
        (Path.home() / "Downloads").resolve(),
        PROJECT_DIR.parent.resolve(),
    ]


def is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def parse_request(uri: str) -> tuple[Path, Path]:
    parsed = urllib.parse.urlsplit(uri)
    if parsed.scheme.lower() != "scad-viewer":
        raise ValueError(f"unsupported URI scheme: {parsed.scheme!r}")
    query = urllib.parse.parse_qs(parsed.query)
    folders = query.get("folder") or []
    models = query.get("model") or []
    if not folders or not models:
        raise ValueError("URI must contain folder and model")
    folder = Path(folders[0]).expanduser().resolve()
    model = (folder / Path(models[0]).name).resolve()
    if not folder.is_dir():
        raise ValueError(f"folder not found: {folder}")
    if model.suffix.lower() != ".stl" or not model.is_file():
        raise ValueError(f"STL not found: {model}")
    if not any(is_under(folder, root) for root in allowed_roots()):
        raise ValueError(f"folder is outside allowed roots: {folder}")
    if not is_under(model, folder):
        raise ValueError("model is outside the requested folder")
    return folder, model


class ViewerHandler(BaseHTTPRequestHandler):
    server_version = "ScadViewer/1.0"

    def log_message(self, fmt: str, *args) -> None:
        LOG.info("%s - %s", self.client_address[0], fmt % args)

    def _respond(
        self,
        status: int,
        content_type: str,
        payload: bytes,
        cache: str = "no-store",
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        self.server.last_request = time.monotonic()
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path

        try:
            if path in ("/", "/viewer", "/viewer.html"):
                self._respond(200, "text/html; charset=utf-8", VIEWER_HTML.read_bytes())
                return

            if path == "/model.stl":
                self._respond(200, "model/stl", self.server.model_path.read_bytes())
                return

            if path == "/source":
                folder = self.server.model_path.parent
                manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
                source = manifest.get("source") or {}
                raw = str(source.get("abs") or "")
                source_path = (
                    Path(raw).resolve()
                    if raw
                    else (folder / str(source.get("rel") or "")).resolve()
                )
                if not source_path.is_file():
                    self._respond(404, "text/plain; charset=utf-8", b"source not found")
                    return
                text = source_path.read_text(encoding="utf-8", errors="replace")
                self._respond(200, "text/plain; charset=utf-8", text.encode("utf-8"))
                return

            if path.startswith("/vendor/"):
                name = path[len("/vendor/"):]
                if name in VENDOR_FILES:
                    target = VENDOR_DIR / name
                    self._respond(
                        200,
                        VENDOR_FILES[name],
                        target.read_bytes(),
                        cache="public, max-age=86400",
                    )
                    return

            if path == "/favicon.ico":
                self._respond(204, "image/x-icon", b"")
                return

            self._respond(404, "text/plain; charset=utf-8", b"not found")
        except OSError as exc:
            LOG.exception("request failed: %s", exc)
            self._respond(500, "text/plain; charset=utf-8", str(exc).encode("utf-8"))


def run_server(folder: Path, model: Path) -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), ViewerHandler)
    server.daemon_threads = True
    server.model_path = model
    server.last_request = time.monotonic()
    port = server.server_address[1]
    LOG.info("started on 127.0.0.1:%s for %s", port, model)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = (
        f"http://127.0.0.1:{port}/viewer?name="
        + urllib.parse.quote(model.name)
    )
    if not open_viewer_browser(url):
        LOG.warning("could not launch viewer for %s", url)

    try:
        while time.monotonic() - server.last_request < IDLE_SECONDS:
            time.sleep(15)
    finally:
        LOG.info("stopping idle viewer server")
        server.shutdown()
        server.server_close()
    return 0


def show_error(message: str) -> None:
    LOG.error("%s", message)
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None, message, "SCAD 3D viewer", 0x10
            )
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        show_error("Usage: viewer_server.py scad-viewer://open?folder=...&model=...")
        return 2
    try:
        folder, model = parse_request(args[0])
    except Exception as exc:
        show_error(f"Не удалось открыть 3D-просмотр:\n\n{exc}")
        return 2
    return run_server(folder, model)


if __name__ == "__main__":
    raise SystemExit(main())
