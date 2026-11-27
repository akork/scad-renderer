"""Local gallery server for in-tab 3D previews.

One hidden loopback server serves any gallery folder under a token URL:

    http://127.0.0.1:<port>/r/<token>/index.html

The gallery and the Three.js viewer share the same origin, so the viewer can
fetch its STL without CORS problems.  The server is started lazily when a
gallery is opened and keeps running for the current session.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .browser import open_in_isolated
from .slots import SLOTS_PAGE

PROJECT_DIR = Path(__file__).resolve().parent.parent
STATE_DIR = PROJECT_DIR / "state"
STATE_PATH = STATE_DIR / "gallery-server.json"
LOG_PATH = STATE_DIR / "gallery-server.log"
VIEWER_DIR = PROJECT_DIR / "viewer"
VIEWER_HTML = VIEWER_DIR / "viewer.html"
VENDOR_DIR = VIEWER_DIR / "vendor"
IDLE_SECONDS = 2 * 60 * 60
VENDOR_TYPES = {
    "three.min.js": "application/javascript",
    "STLLoader.js": "application/javascript",
    "OrbitControls.js": "application/javascript",
}
DEFAULT_PORT = 8765
PING_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

LOG = logging.getLogger("scad-gallery-server")


def setup_logging() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG.setLevel(logging.INFO)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s"))
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


def encode_folder(folder: Path) -> str:
    return base64.urlsafe_b64encode(str(folder.resolve()).encode("utf-8")).decode("ascii").rstrip("=")


def decode_folder(token: str) -> Path:
    padded = token + "=" * (-len(token) % 4)
    return Path(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")).resolve()


def read_state() -> dict:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _health(port: int, timeout: float = 0.4) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/health", timeout=timeout
        ) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data.get("app") == "scad-gallery"
    except Exception:
        return False


def ensure_server(port: int = DEFAULT_PORT) -> tuple[str, int]:
    state = read_state()
    if int(state.get("port") or 0) == port and _health(port):
        return f"http://127.0.0.1:{port}", port

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        STATE_PATH.unlink(missing_ok=True)
    except OSError:
        pass
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    executable = pythonw if pythonw.is_file() else Path(sys.executable)
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [
            str(executable),
            "-m",
            "scadvariants.gallery_server",
            "--serve",
            "--port",
            str(port),
        ],
        cwd=str(PROJECT_DIR),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = read_state()
        if int(state.get("port") or 0) == port and _health(port):
            return f"http://127.0.0.1:{port}", port
        time.sleep(0.2)
    raise RuntimeError("gallery server did not start")


def gallery_url(index_path: Path) -> str:
    index_path = index_path.resolve()
    base, _ = ensure_server()
    return f"{base}/r/{encode_folder(index_path.parent)}/index.html"


def viewer_url(folder: Path, model: str) -> str:
    folder = folder.resolve()
    base, _ = ensure_server()
    model_name = urllib.parse.quote(Path(model).name)
    return f"{base}/r/{encode_folder(folder)}/viewer.html?name={model_name}"


def open_gallery_page(index_path: Path) -> bool:
    url = gallery_url(index_path)
    return open_in_isolated(
        url,
        profile_name="browser-profile",
        app_mode=False,
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "ScadGallery/1.0"

    def log_message(self, fmt: str, *args) -> None:
        LOG.info("%s - %s", self.client_address[0], fmt % args)

    def _send(
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

    def _file(self, path: Path, cache: str = "no-store") -> None:
        suffix = path.suffix.lower()
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".png": "image/png",
            ".stl": "model/stl",
            ".js": "application/javascript",
            ".css": "text/css",
            ".json": "application/json",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
        }.get(suffix) or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self._send(200, content_type, path.read_bytes(), cache=cache)

    def do_GET(self) -> None:  # noqa: N802
        self.server.last_request = time.monotonic()
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path

        if path == "/health":
            payload = json.dumps(
                {"app": "scad-gallery", "pid": os.getpid(), "port": self.server.server_port}
            ).encode("utf-8")
            self._send(200, "application/json", payload)
            return

        if path == "/ping.png":
            self._send(200, "image/png", PING_PNG)
            return

        if path == "/source":
            query = urllib.parse.parse_qs(parsed.query)
            tokens = query.get("folder") or []
            if not tokens:
                self._send(400, "text/plain; charset=utf-8", "folder missing".encode("utf-8"))
                return
            try:
                folder = decode_folder(tokens[0])
            except Exception:
                self._send(400, "text/plain; charset=utf-8", "bad token".encode("utf-8"))
                return
            if not folder.is_dir() or not any(is_under(folder, root) for root in allowed_roots()):
                self._send(403, "text/plain; charset=utf-8", "forbidden".encode("utf-8"))
                return
            try:
                manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
                source = manifest.get("source") or {}
                raw = str(source.get("abs") or "")
                if raw:
                    source_path = Path(raw).resolve()
                else:
                    source_path = (folder / str(source.get("rel") or "")).resolve()
            except Exception:
                self._send(404, "text/plain; charset=utf-8", "source not found".encode("utf-8"))
                return
            if not source_path.is_file() or not any(
                is_under(source_path, root) for root in allowed_roots()
            ):
                self._send(404, "text/plain; charset=utf-8", "source not found".encode("utf-8"))
                return
            try:
                text = source_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                self._send(500, "text/plain; charset=utf-8", "source unreadable".encode("utf-8"))
                return
            self._send(200, "text/plain; charset=utf-8", text.encode("utf-8"))
            return

        if path in ("/slots", "/slots/"):
            if SLOTS_PAGE.is_file():
                self._file(SLOTS_PAGE)
            else:
                self._send(404, "text/plain", b"slots page not found")
            return

        if path.startswith("/vendor/"):
            name = path[len("/vendor/"):]
            if name in VENDOR_TYPES:
                self._file(VENDOR_DIR / name, cache="public, max-age=86400")
                return
            self._send(404, "text/plain", b"not found")
            return

        if not path.startswith("/r/"):
            self._send(404, "text/plain", b"not found")
            return

        rest = path[len("/r/"):]
        token, _, rel = rest.partition("/")
        if not token:
            self._send(404, "text/plain", b"not found")
            return
        try:
            folder = decode_folder(token)
        except Exception:
            self._send(400, "text/plain", b"bad token")
            return
        if not folder.is_dir() or not any(is_under(folder, root) for root in allowed_roots()):
            self._send(403, "text/plain", b"forbidden")
            return

        rel = urllib.parse.unquote(rel)
        if not rel:
            rel = "index.html"
        if rel == "viewer.html":
            self._file(VIEWER_HTML)
            return
        if rel == "model.stl":
            query = urllib.parse.parse_qs(parsed.query)
            names = query.get("name") or []
            if not names:
                self._send(400, "text/plain", b"model name missing")
                return
            model = (folder / Path(names[0]).name).resolve()
            if model.suffix.lower() != ".stl" or not model.is_file() or not is_under(model, folder):
                self._send(404, "text/plain", b"model not found")
                return
            self._file(model)
            return

        target = (folder / rel).resolve()
        if not is_under(target, folder) or not target.is_file():
            self._send(404, "text/plain", b"not found")
            return
        self._file(target)


def serve(port: int = 0) -> int:
    setup_logging()
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        if port and _health(port):
            return 0
        raise
    server.daemon_threads = True
    server.last_request = time.monotonic()
    port = server.server_port
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "app": "scad-gallery",
        "pid": os.getpid(),
        "port": port,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    tmp = STATE_PATH.with_name(f".{STATE_PATH.name}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, STATE_PATH)

    def watchdog() -> None:
        while True:
            time.sleep(30)
            if time.monotonic() - server.last_request > IDLE_SECONDS:
                LOG.info("gallery server idle; stopping")
                server.shutdown()
                return

    threading.Thread(target=watchdog, daemon=True).start()
    LOG.info("gallery server on 127.0.0.1:%s", port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        try:
            current = read_state()
            if int(current.get("pid") or 0) == os.getpid():
                STATE_PATH.unlink(missing_ok=True)
        except OSError:
            pass
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--serve" in args:
        port = 0
        if "--port" in args:
            try:
                port = int(args[args.index("--port") + 1])
            except (IndexError, ValueError):
                port = 0
        return serve(port)
    if len(args) == 1:
        return 0 if open_gallery_page(Path(args[0])) else 1
    print("usage: gallery_server.py --serve [--port N] | <index.html>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
