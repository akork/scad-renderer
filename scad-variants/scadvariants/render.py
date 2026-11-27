from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

try:  # Pillow is optional: the watcher still works without the pretty footer.
    from PIL import Image, ImageChops, ImageDraw, ImageFont
    _HAS_PIL = True
except Exception:  # pragma: no cover - depends on the local Python
    Image = ImageChops = ImageDraw = ImageFont = None  # type: ignore[assignment]
    _HAS_PIL = False


@dataclass(slots=True)
class RenderSettings:
    openscad: str
    width: int = 1200
    height: int = 900
    camera: str = "0,0,0,55,0,25,0"
    colorscheme: str = "Tomorrow"
    projection: str = "p"
    mesh: bool = True
    timeout: float = 300.0
    pretty: bool = True
    footer: bool = False
    font_path: str | None = None

    def png_config(self) -> dict[str, object]:
        return {
            "width": self.width,
            "height": self.height,
            "camera": self.camera,
            "colorscheme": self.colorscheme,
            "projection": self.projection,
            "pretty": bool(self.pretty and _HAS_PIL),
            "footer": bool(self.footer),
            "footer_version": 3,
        }

    def stl_config(self) -> dict[str, object]:
        # One OpenSCAD invocation writes both PNG and STL, so the geometry is
        # evaluated once.  OpenSCAD's default .stl writer is ASCII STL; slicers
        # accept it.  Binary would require a second invocation (or conversion).
        return {"mesh": True, "format": "openscad-default-stl", "single_run": True}


@dataclass(slots=True)
class RenderResult:
    ok: bool
    image: Path | None
    mesh: Path | None
    duration_s: float
    log: str
    error: str | None = None


def _tools_root() -> Path:
    # ...\harness\scad-variants\scadvariants\render.py -> ...\harness\tools
    return Path(__file__).resolve().parents[2] / "tools"


def _nightly_candidates() -> Iterable[Path]:
    tools = _tools_root()
    if not tools.is_dir():
        return
    for entry in sorted(
        tools.glob("openscad-*/openscad.exe"), reverse=True
    ):
        if entry.is_file():
            yield entry


def _candidate_paths() -> Iterable[Path]:
    env = os.environ.get("OPENSCAD")
    if env:
        yield Path(env)

    # Portable layout: keep OpenSCAD next to the app/launcher if desired.
    for base in (
        Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else None,
        Path(__file__).resolve().parents[2],
    ):
        if base is not None:
            yield base / "openscad" / "openscad.exe"
            yield base / "openscad.exe"

    yield from _nightly_candidates()

    exe = shutil.which("openscad")
    if exe:
        yield Path(exe)

    for base in (
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("LOCALAPPDATA"),
    ):
        if not base:
            continue
        yield Path(base) / "OpenSCAD" / "openscad.exe"
        yield Path(base) / "Programs" / "OpenSCAD" / "openscad.exe"

    # Per-user Scoop and machine-wide Chocolatey installs.
    yield Path.home() / "scoop" / "shims" / "openscad.exe"
    program_data = os.environ.get("ProgramData")
    if program_data:
        yield Path(program_data) / "chocolatey" / "bin" / "openscad.exe"


def find_openscad(explicit: str | None = None) -> str:
    if explicit:
        path = Path(explicit)
        if path.is_file():
            return str(path)
        found = shutil.which(explicit)
        if found:
            return found
        raise FileNotFoundError(f"OpenSCAD not found: {explicit}")
    for candidate in _candidate_paths():
        if candidate and candidate.is_file():
            return str(candidate)
    raise FileNotFoundError(
        "OpenSCAD not found. Install it or pass --openscad PATH."
    )


def openscad_version(executable: str) -> str:
    try:
        proc = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
    except Exception as exc:  # pragma: no cover - environment specific
        return f"unknown ({exc})"
    out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return out or f"unknown (exit {proc.returncode})"


def _escape_scad_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _short_path(path: Path) -> str:
    """Return an ASCII 8.3 path on Windows when one exists.

    OpenSCAD 2021.01 passes paths to its own file APIs as 8-bit strings and
    turns Cyrillic/Unicode directory names into "????".  Short paths keep the
    command line and output locations ASCII while the files themselves stay
    where the user expects them.
    """
    if os.name != "nt":
        return str(path)
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetShortPathNameW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_ulong,
        ]
        kernel32.GetShortPathNameW.restype = ctypes.c_ulong
        buffer = ctypes.create_unicode_buffer(32768)
        length = kernel32.GetShortPathNameW(str(path), buffer, 32768)
        return buffer.value if length else str(path)
    except Exception:
        return str(path)


def _define_args(values: dict[str, str]) -> list[str]:
    args: list[str] = []
    for name, value in values.items():
        args.extend(["-D", f'{name}="{_escape_scad_string(value)}"'])
    return args


def _run(
    cmd: Sequence[str],
    cwd: Path,
    timeout: float,
) -> tuple[int, str]:
    try:
        proc = subprocess.Popen(
            list(cmd),
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        return 127, f"{type(exc).__name__}: {exc}"
    try:
        out, err = proc.communicate(timeout=timeout)
        log = ((out or "") + (err or "")).strip()
        return proc.returncode, log
    except subprocess.TimeoutExpired:
        # subprocess.run() on Windows can leave the child alive in some
        # environments.  Kill the whole tree explicitly and reap it.
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        else:
            proc.kill()
        try:
            out, err = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            out, err = "", ""
        detail = ((out or "") + (err or "")).strip()
        msg = f"timeout after {timeout:.0f}s"
        if detail:
            msg += "\n" + detail[-4000:]
        return 124, msg


def _valid_png(path: Path) -> bool:
    try:
        if path.stat().st_size < 64:
            return False
        with path.open("rb") as f:
            return f.read(8) == b"\x89PNG\r\n\x1a\n"
    except OSError:
        return False


def _valid_stl(path: Path) -> bool:
    try:
        size = path.stat().st_size
        if size < 100:
            return False
        # Binary STL.
        with path.open("rb") as f:
            header = f.read(84)
        if len(header) == 84:
            n = int.from_bytes(header[80:84], "little")
            if n > 0 and size >= 84 + n * 50:
                return True
        # ASCII STL, which is what a single-run PNG+STL export produces.
        with path.open("rb") as f:
            head = f.read(16384)
        return head.lstrip().startswith(b"solid") and b"facet" in head
    except OSError:
        return False


# ---------------------------------------------------------------------------
#  Pretty preview image
# ---------------------------------------------------------------------------

_BG = (244, 246, 248)
_FOOTER = (17, 24, 39)
_LABEL = (248, 250, 252)
_SUBTITLE = (148, 163, 184)


def _font(size: int, path: str | None = None):
    if not _HAS_PIL:
        return None
    choices = [path] if path else []
    choices += [
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for item in choices:
        if not item:
            continue
        try:
            return ImageFont.truetype(item, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _text_width(draw, text: str, font) -> float:
    if hasattr(draw, "textlength"):
        return draw.textlength(text, font=font)
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    return right - left


def _fit_text(draw, text: str, max_width: int, start_size: int, font_path: str | None):
    size = start_size
    while size >= 14:
        font = _font(size, font_path)
        if _text_width(draw, text, font) <= max_width:
            return text, font
        size -= 2
    font = _font(14, font_path)
    suffix = "..."
    while text and _text_width(draw, text + suffix, font) > max_width:
        text = text[:-1]
    return text + suffix, font


def finalize_image(
    raw_path: Path,
    out_path: Path,
    label: str,
    subtitle: str,
    settings: RenderSettings,
    temp_dir: Path | None = None,
    footer: bool = True,
) -> None:
    """Trim the render, put it on a light canvas and optionally add a footer."""
    if not (_HAS_PIL and settings.pretty):
        os.replace(raw_path, out_path)
        return

    temp_parent = temp_dir if temp_dir is not None else out_path.parent
    temp_parent.mkdir(parents=True, exist_ok=True)
    temp_out = temp_parent / f".{out_path.name}.{uuid.uuid4().hex[:8]}.tmp"
    saved = False
    try:
        img = Image.open(raw_path).convert("RGB")
        bg = img.getpixel((2, 2))
        diff = ImageChops.difference(img, Image.new("RGB", img.size, bg)).convert("L")
        mask = diff.point(lambda p: 255 if p > 10 else 0)
        bbox = mask.getbbox()
        if bbox and (bbox[2] - bbox[0]) > 4 and (bbox[3] - bbox[1]) > 4:
            pad = max(8, int(max(bbox[2] - bbox[0], bbox[3] - bbox[1]) * 0.04))
            bbox = (
                max(0, bbox[0] - pad),
                max(0, bbox[1] - pad),
                min(img.width, bbox[2] + pad),
                min(img.height, bbox[3] + pad),
            )
            img = img.crop(bbox)
        # Very light backgrounds look neutral in the gallery.
        img = ImageChops.multiply(img, Image.new("RGB", img.size, (252, 252, 252)))

        W, H = settings.width, settings.height
        footer_h = max(86, int(H * 0.105)) if footer else 0
        top = 24
        content_w = W - 72
        content_h = H - footer_h - top - 20
        scale = min(content_w / img.width, content_h / img.height)
        new_size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
        img = img.resize(new_size, Image.Resampling.LANCZOS)

        canvas = Image.new("RGB", (W, H), _BG)
        x = (W - img.width) // 2
        y = top + (content_h - img.height) // 2
        canvas.paste(img, (x, y))

        if footer:
            draw = ImageDraw.Draw(canvas)
            draw.rectangle((0, H - footer_h, W, H), fill=_FOOTER)
            max_text = W - 72
            label_text, label_font = _fit_text(
                draw, label, max_text, max(26, int(footer_h * 0.40)), settings.font_path
            )
            sub_text, sub_font = _fit_text(
                draw, subtitle, max_text, max(16, int(footer_h * 0.21)), settings.font_path
            )
            draw.text((36, H - footer_h + 14), label_text, font=label_font, fill=_LABEL)
            draw.text(
                (36, H - footer_h + footer_h - 34),
                sub_text,
                font=sub_font,
                fill=_SUBTITLE,
            )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(temp_out, format="PNG", optimize=True)
        os.replace(temp_out, out_path)
        saved = True
        raw_path.unlink(missing_ok=True)
    except Exception:
        # Never lose a valid render because cosmetic post-processing failed.
        try:
            temp_out.unlink(missing_ok=True)
        except OSError:
            pass
        if not saved:
            os.replace(raw_path, out_path)
        else:
            raw_path.unlink(missing_ok=True)


def make_contact_sheet(
    images: Sequence[Path],
    out_path: Path,
    title: str,
    settings: RenderSettings,
) -> bool:
    if not _HAS_PIL or not images:
        return False
    try:
        n = len(images)
        if n == 1:
            cols, card_w, card_h = 1, 760, 570
        elif n == 2:
            cols, card_w, card_h = 2, 500, 375
        else:
            cols, card_w, card_h = 3, 380, 285
        gap = 22
        left = 30
        header = 92
        rows = (n + cols - 1) // cols
        W = left * 2 + cols * card_w + (cols - 1) * gap
        H = header + rows * card_h + (rows - 1) * gap + 28
        sheet = Image.new("RGB", (W, H), (250, 251, 252))
        draw = ImageDraw.Draw(sheet)
        title_font = _font(38, settings.font_path)
        draw.text((left, 26), title, font=title_font, fill=(17, 24, 39))
        for i, image_path in enumerate(images):
            if not image_path.is_file():
                continue
            thumb = Image.open(image_path).convert("RGB")
            thumb.thumbnail((card_w, card_h), Image.Resampling.LANCZOS)
            x = left + (i % cols) * (card_w + gap)
            y = header + (i // cols) * (card_h + gap)
            sheet.paste(thumb, (x + (card_w - thumb.width) // 2, y))
        temp_dir = out_path.parent / "tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_out = temp_dir / f".{out_path.name}.{uuid.uuid4().hex[:8]}.tmp"
        sheet.save(temp_out, format="PNG", optimize=True)
        os.replace(temp_out, out_path)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
#  Public rendering entry point
# ---------------------------------------------------------------------------

def render_variant(
    source: Path,
    values: dict[str, str],
    image_path: Path,
    stl_path: Path | None,
    label: str,
    subtitle: str,
    settings: RenderSettings,
) -> RenderResult:
    started = time.time()
    image_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = image_path.parent / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_image = temp_dir / f"image-{uuid.uuid4().hex[:8]}.png"
    temp_stl: Path | None = None
    logs: list[str] = []
    error: str | None = None
    want_stl = bool(settings.mesh and stl_path is not None)
    if want_stl:
        stl_path.parent.mkdir(parents=True, exist_ok=True)
        temp_stl = temp_dir / f"mesh-{uuid.uuid4().hex[:8]}.stl"

    # OpenSCAD 2021.01 mangles non-ASCII paths to "????" internally.  Pass
    # ASCII 8.3 short paths to the subprocess, but keep reading/moving files
    # through the normal long paths in Python.
    short_temp_dir = _short_path(temp_dir)
    short_image = Path(short_temp_dir) / temp_image.name
    short_stl = (
        Path(short_temp_dir) / temp_stl.name if temp_stl is not None else None
    )
    short_source = _short_path(source)
    short_cwd = Path(_short_path(source.parent))

    # OpenSCAD accepts repeated -o arguments.  If both PNG and STL are asked
    # for, the geometry is evaluated once and then written in both formats.
    # Do not pass --export-format here: it is global and would turn the PNG
    # output into STL as well.
    outputs = ["-o", str(short_image)]
    if short_stl is not None:
        outputs += ["-o", str(short_stl)]
    cmd = [
        settings.openscad,
        *outputs,
        f"--imgsize={settings.width},{settings.height}",
        "--viewall",
        "--autocenter",
        f"--camera={settings.camera}",
        f"--colorscheme={settings.colorscheme}",
        f"--projection={settings.projection}",
        *_define_args(values),
        short_source,
    ]
    try:
        rc, log = _run(cmd, short_cwd, settings.timeout)
        if log:
            logs.append(log)
        image_ok = _valid_png(temp_image)
        stl_ok = (not want_stl) or (
            temp_stl is not None and _valid_stl(temp_stl)
        )
        if rc == 124:
            error = f"OpenSCAD timeout after {settings.timeout:.0f}s"
        elif rc != 0 or not image_ok:
            error = f"OpenSCAD run failed (exit {rc}): PNG is missing/invalid"
        elif not stl_ok:
            error = f"OpenSCAD run failed (exit {rc}): STL is missing/invalid"
        else:
            finalize_image(
                temp_image,
                image_path,
                label,
                subtitle,
                settings,
                temp_dir=temp_dir,
                footer=settings.footer,
            )
            if not _valid_png(image_path):
                error = "output PNG is invalid"
            elif temp_stl is not None:
                os.replace(temp_stl, stl_path)
    except Exception as exc:  # pragma: no cover - I/O edge cases
        error = f"{type(exc).__name__}: {exc}"
    finally:
        temp_image.unlink(missing_ok=True)
        if temp_stl is not None:
            temp_stl.unlink(missing_ok=True)

    duration = time.time() - started
    full_log = "\n".join(x for x in logs if x)
    if len(full_log) > 12000:
        full_log = full_log[-12000:]
    return RenderResult(
        ok=error is None,
        image=image_path if error is None else None,
        mesh=(
            stl_path
            if (error is None and want_stl and stl_path and stl_path.exists())
            else None
        ),
        duration_s=duration,
        log=full_log,
        error=error,
    )
