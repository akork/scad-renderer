from __future__ import annotations

import base64
import html
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .slots import SLICER_LABELS, load_all_slots, slots_page_path, write_slots_page

try:
    from zoneinfo import ZoneInfo

    MSK = ZoneInfo("Europe/Moscow")
except Exception:  # pragma: no cover - Windows without tzdata
    MSK = timezone(timedelta(hours=3), "MSK")


_CSS = r"""
:root {
  --bg: #f4f6f9;
  --panel: #ffffff;
  --line: #e2e8f0;
  --ink: #111827;
  --muted: #64748b;
  --accent: #0f766e;
  --accent-soft: #ccfbf1;
  --warn: #b45309;
  --warn-soft: #fef3c7;
  --bad: #b91c1c;
  --bad-soft: #fee2e2;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font-family: "Segoe UI", Inter, system-ui, -apple-system, sans-serif;
  line-height: 1.45;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.wrap { max-width: 1460px; margin: 0 auto; padding: 30px 28px 70px; }
.hero {
  background: linear-gradient(135deg, #0f172a, #134e4a);
  color: #f8fafc; border-radius: 22px; padding: 34px 38px;
  display: flex; justify-content: space-between; gap: 24px; align-items: flex-end;
  box-shadow: 0 18px 40px rgba(15, 23, 42, .18);
}
.hero h1 { margin: 0 0 8px; font-size: 32px; letter-spacing: -.02em; }
.hero p { margin: 0; color: #cbd5e1; max-width: 780px; }
.hero .meta { text-align: right; color: #99f6e4; font-size: 13px; white-space: nowrap; }
.btn {
  display: inline-flex; align-items: center; gap: 8px; border: 1px solid #99f6e4;
  color: #ccfbf1; background: rgba(255,255,255,.05); border-radius: 999px;
  padding: 9px 16px; font: inherit; font-size: 14px; cursor: pointer;
}
.btn:hover { background: rgba(255,255,255,.12); }
.project { margin-top: 38px; }
.project h2 { font-size: 21px; margin: 0 0 16px; display: flex; align-items: baseline; gap: 12px; }
.project h2 span { font-size: 13px; color: var(--muted); font-weight: 500; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr)); gap: 22px; }
.card {
  background: var(--panel); border: 1px solid var(--line); border-radius: 16px;
  overflow: hidden; box-shadow: 0 2px 7px rgba(15,23,42,.04);
  transition: transform .13s ease, box-shadow .13s ease;
}
.card:hover { transform: translateY(-2px); box-shadow: 0 10px 24px rgba(15,23,42,.10); }
.card .thumb { display: block; background: #f1f5f9; }
.card .thumb img { display: block; width: 100%; aspect-ratio: 4 / 3; object-fit: cover; }
.card .body { padding: 15px 17px 17px; }
.card h3 { margin: 0 0 4px; font-size: 17px; }
.path { color: var(--muted); font-size: 12.5px; word-break: break-all; }
.meta-row { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 12px; align-items: center; }
.badge {
  display: inline-flex; align-items: center; border-radius: 999px;
  padding: 3px 9px; font-size: 12px; font-weight: 600;
}
.ok { color: #065f46; background: var(--accent-soft); }
.partial { color: var(--warn); background: var(--warn-soft); }
.error { color: var(--bad); background: var(--bad-soft); }
.chip {
  display: inline-block; border: 1px solid var(--line); border-radius: 7px;
  padding: 2px 7px; font-size: 12px; color: #334155; background: #f8fafc;
}
.chip b { color: #0f172a; }
.chip.stl { color: #0f766e; border-color: #99f6e4; background: #f0fdfa; font-weight: 700; }
.source-head {
  margin-top: 22px; background: var(--panel); border: 1px solid var(--line);
  border-radius: 16px; padding: 20px 22px;
}
.source-head h1 { margin: 0 0 4px; font-size: 26px; }
.source-head .sub { color: var(--muted); font-size: 13px; }
.switches { margin-top: 16px; display: grid; gap: 10px; }
.switch { display: flex; flex-wrap: wrap; gap: 7px; align-items: center; font-size: 13px; }
.switch .name { font-weight: 700; min-width: 80px; }
.notice { border-radius: 12px; padding: 14px 16px; margin-top: 16px; font-size: 14px; }
.notice.bad { color: var(--bad); background: var(--bad-soft); border: 1px solid #fecaca; }
.notice.warn { color: var(--warn); background: var(--warn-soft); border: 1px solid #fde68a; }
.variant-card .body { padding-bottom: 14px; }
.variant-card .label { font-size: 14px; font-weight: 650; margin: 0; }
.variant-card .stamp { color: var(--muted); font-size: 12px; margin-top: 4px; }
.variant-card .stale { color: var(--warn); font-size: 12px; margin-top: 5px; }
.empty { color: var(--muted); background: var(--panel); border: 1px dashed var(--line); border-radius: 14px; padding: 30px; }
.footer { color: var(--muted); font-size: 12px; margin-top: 40px; }
#source-panel { display: none; min-height: 0; }
body.code-mode { overflow: hidden; }
body.code-mode .wrap {
  max-width: none; height: 100vh; padding: 18px 22px 20px;
  display: grid; grid-template-columns: minmax(300px, 1fr) minmax(0, 2fr);
  grid-template-rows: auto auto minmax(0, 1fr); gap: 12px 18px;
}
body.code-mode .toolbar { grid-column: 1 / -1; margin-top: 0; }
body.code-mode .source-head { grid-column: 1; grid-row: 2; margin-top: 0; }
body.code-mode .project {
  grid-column: 1; grid-row: 3; margin-top: 0; min-height: 0;
  overflow-y: auto; padding-right: 6px;
}
body.code-mode .grid { grid-template-columns: 1fr; gap: 14px; }
body.code-mode .footer { display: none; }
body.code-mode #source-panel {
  display: flex; grid-column: 2; grid-row: 2 / 4;
  flex-direction: column; min-height: 0; overflow: hidden;
  background: #0b1220; border: 1px solid #1e293b; border-radius: 14px;
}
.code-head {
  display: flex; align-items: center; gap: 8px; padding: 10px 12px;
  background: #0f172a; border-bottom: 1px solid #1e293b; color: #cbd5e1;
  font-size: 12px;
}
.code-head .code-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: Consolas, monospace; }
.code-head button {
  border: 1px solid rgba(148,163,184,.4); border-radius: 7px;
  background: #111c30; color: #e2e8f0; padding: 6px 9px;
  font: inherit; font-size: 12px; cursor: pointer;
}
.code-head button:hover { background: #1e293b; }
#source-code {
  flex: 1; min-height: 0; margin: 0; padding: 14px 16px 24px; overflow: auto;
  color: #dbeafe; background: #0b1220;
  font-family: Consolas, "Cascadia Mono", monospace; font-size: 12.5px;
  line-height: 1.55; white-space: pre; tab-size: 4;
}
#source-code .tok-com { color: #64748b; font-style: italic; }
#source-code .tok-str { color: #86efac; }
#source-code .tok-num { color: #fbbf24; }
#source-code .tok-kw { color: #67e8f9; font-weight: 600; }
.btn.active-code { border-color: #0f766e !important; background: #0f766e !important; color: #fff !important; }
.toolbar { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-top: 22px; }
.toolbar .crumbs { color: var(--muted); font-size: 13px; }
.copy-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.copy-btn {
  border: 1px solid var(--line); background: #fff; color: #334155;
  border-radius: 9px; padding: 6px 9px; font: inherit; font-size: 12px;
  cursor: pointer;
}
.copy-btn:hover { border-color: #94a3b8; background: #f8fafc; }
.copy-path {
  display: block; width: 100%; border: 0; border-top: 1px solid var(--line);
  background: #0f766e; color: #fff; padding: 11px 12px;
  font: inherit; font-size: 13px; font-weight: 700; cursor: pointer;
}
.copy-path:hover { background: #115e59; }
.slot-box { display: flex; flex-direction: column; }
.slot-pills {
  display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
  padding: 9px 12px; border-top: 1px solid var(--line); background: #f8fafc;
}
.slot-pill {
  border: 1px solid #cbd5e1; border-radius: 999px; background: #fff;
  color: #334155; padding: 6px 12px; font: inherit; font-size: 12px;
  font-weight: 650; cursor: pointer; max-width: 130px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.slot-pill:hover { border-color: #94a3b8; }
.slot-pill[hidden] { display: none; }
.slot-pill.active { border-color: #0f766e; background: #0f766e; color: #fff; }
.slot-more {
  width: 30px; height: 30px; margin-left: auto; border: 1px solid #cbd5e1;
  border-radius: 50%; background: #fff; color: #334155; font: inherit;
  font-size: 16px; line-height: 1; cursor: pointer; flex: 0 0 auto;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.slot-more:hover { border-color: #0f766e; color: #0f766e; }
.slot-more.active { background: #0f766e; border-color: #0f766e; color: #fff; width: auto; border-radius: 999px; padding: 0 9px; }
.slot-empty { color: #94a3b8; font-size: 11px; }
.slot-value { display: none; }
.slot-send {
  display: block; width: 100%; border: 0; border-top: 1px solid var(--line);
  background: #0f766e; color: #fff; padding: 22px 14px;
  font: inherit; font-size: 15px; font-weight: 700; cursor: pointer;
  line-height: 1.2; min-height: 70px;
}
.slot-send:hover { background: #115e59; }
.slicer-box { display: flex; flex-direction: column; }
.slicer-pills {
  display: flex; flex-wrap: wrap; gap: 6px; padding: 9px 12px;
  border-top: 1px solid var(--line); background: #f8fafc;
}
.slicer-pill {
  border: 1px solid #cbd5e1; border-radius: 999px; background: #fff;
  color: #334155; padding: 6px 14px; font: inherit; font-size: 12px;
  font-weight: 650; cursor: pointer;
}
.slicer-pill:hover { border-color: #94a3b8; }
.slicer-pill.active { border-color: #0f766e; background: #0f766e; color: #fff; }
.slicer-value { display: none; }
.open-slicer {
  display: block; width: 100%; border: 0; border-top: 1px solid var(--line);
  background: #0f766e; color: #fff; padding: 22px 14px;
  font: inherit; font-size: 15px; font-weight: 700; cursor: pointer;
  line-height: 1.2; min-height: 70px;
}
.open-slicer:hover { background: #115e59; }
#slot-dialog {
  width: min(440px, 92vw); border: 1px solid var(--line); border-radius: 14px;
  padding: 18px; background: #fff; color: var(--ink);
}
#slot-dialog::backdrop { background: rgba(15, 23, 42, .45); }
#slot-dialog h3 { margin: 0 0 12px; font-size: 17px; }
#slot-dialog-list { display: flex; flex-wrap: wrap; gap: 7px; max-height: 280px; overflow: auto; }
.slot-dialog-item {
  border: 1px solid #cbd5e1; border-radius: 999px; background: #fff;
  color: #334155; padding: 7px 12px; font: inherit; font-size: 12px; cursor: pointer;
}
.slot-dialog-item.active { background: #0f766e; border-color: #0f766e; color: #fff; }
#slot-dialog-new { display: flex; gap: 6px; margin-top: 14px; }
#slot-new-name {
  flex: 1; min-width: 0; border: 1px solid var(--line); border-radius: 8px;
  padding: 8px 9px; font: inherit; font-size: 13px;
}
#slot-dialog-close {
  margin-top: 12px; border: 1px solid var(--line); border-radius: 8px;
  background: #fff; color: #334155; padding: 7px 11px; font: inherit; font-size: 12px; cursor: pointer;
}
#image-overlay {
  position: fixed; inset: 0; z-index: 9000; display: none;
  align-items: center; justify-content: center; padding: 24px;
  background: rgba(15, 23, 42, .86);
}
#image-overlay.show { display: flex; }
#image-overlay img {
  max-width: 96vw; max-height: 94vh; border-radius: 10px;
  background: #fff; box-shadow: 0 24px 70px rgba(0, 0, 0, .5);
}
body.image-open { overflow: hidden; }
.thumb-wrap { position: relative; }
.thumb { position: relative; display: block; }
.viewer-link { cursor: url("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAACPElEQVR4nGNgGOmAkRTF/OJa/3HJfXx5jZFmDuDHYzGlDmEkxeKXjy99w6VWXFaPixyHMBJjOT6L8TmEGEcwkmr54w9MGOplBf6R7QhGYi3HZjE+hxDrCCZcEqRajq6O2GhjwuZ7cizH5wh8uYiJkGE3rl9j8nV347QxNeGqLClm//PnD8OxI0eYTXR1uEDYxc6Wsyg3h/3xo0eM5DiaCZ/vQUBDU+vf5p27vrd1df/cvXMn86kTx5lhcuu3bvs+a/6Cn48ePmQszstl//v3L4YFhEKBCZ/vYeD///8MIMjExMQgLiGBYpCSsvK/tMys3/fu3mUCYWz68QEWYhSF+PlyPHzwgMnT2+ePopLyv5cvXsJDAQQkpaXAjnr39i3JxTELMYrWbNr84+aN60yJ0dEchibG/yQkJFFC4dGDh2DvSsvIoBYIRAAmYhQxMjIycHFx/QfRf37/RpG7d+cO09xZM1mtbe3+ysjKEl1nEB0Ca1auZOnv7mJjZmH57+Dk9Nc/KPjP2dOnwVEQ6O3FKSwi8t/a1vZvYWkZqsuIBIzULAMIlYrYSkQmGAMmiV6rUQrwWY7iAGwAvZIhFpCijwmZgy0USHUEsUGP1QHIgBxH4KoN8QEmdAFk16I7ApdD0OWQ9bX29A1ci6gVyfKcWA9GurYJW7H4HJsjGPE5AJdD8AHkKJyyeMd/Qo5gJNZgQg7BldIJOYKRgQ4AnyOY6OEAbHEPcxQjPRyAbikyYKKnA9BDAlfWpDlADgkA8/og0XniUscAAAAASUVORK5CYII=") 14 14, grab; }
.viewer-link:active { cursor: grabbing; }
.thumb-expand {
  position: absolute; top: 10px; right: 10px; z-index: 3;
  width: 40px; height: 40px; display: flex; align-items: center;
  justify-content: center; border: 0; border-radius: 9px;
  background: rgba(2, 6, 23, .78); color: #fff; cursor: zoom-in;
  box-shadow: 0 2px 8px rgba(0,0,0,.2);
}
.thumb-expand:hover { background: #0f766e; }
.thumb-expand svg { width: 24px; height: 24px; }
#viewer-overlay {
  position: fixed; inset: 0; z-index: 9100; display: none;
  align-items: center; justify-content: center; padding: 24px;
  background: rgba(15, 23, 42, .72);
}
#viewer-overlay.show { display: flex; }
#viewer-frame {
  width: 100%; height: 100%; border: 0; border-radius: 12px;
  background: #0b1220; box-shadow: 0 20px 60px rgba(0, 0, 0, .45);
}
#viewer-overlay-close {
  position: absolute; top: 30px; right: 34px; z-index: 2;
  width: 38px; height: 38px; border: 1px solid rgba(255,255,255,.35);
  border-radius: 50%; background: rgba(2, 6, 23, .8); color: #fff;
  font-size: 24px; line-height: 1; cursor: pointer;
}
#viewer-overlay-close:hover { background: #0f766e; }
body.viewer-open { overflow: hidden; }
#copy-toast {
  position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%);
  max-width: min(90vw, 900px); background: #0f172a; color: #fff;
  border-radius: 10px; padding: 10px 14px; font-size: 13px;
  opacity: 0; pointer-events: none; transition: opacity .18s ease;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; z-index: 9999;
}
#copy-toast.show { opacity: .96; }
@media (max-width: 720px) {
  .wrap { padding: 18px 15px 50px; }
  .hero { padding: 24px 22px; display: block; }
  .hero .meta { text-align: left; margin-top: 16px; }
  .hero h1 { font-size: 25px; }
}
"""


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _format_dt(value: Any) -> str:
    """Format ISO timestamps as readable Moscow time."""
    if not value:
        return ""
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=MSK)
    return parsed.astimezone(MSK).strftime("%d.%m.%Y %H:%M")


def _ru(count: int, one: str, few: str, many: str) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return f"{count} {one}"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return f"{count} {few}"
    return f"{count} {many}"


def _href(path: str) -> str:
    return html.escape(
        quote(path.replace("\\", "/"), safe="/%:._~-"),
        quote=True,
    )


def _rel_link(target: Path, start: Path) -> str:
    try:
        rel = os.path.relpath(target, start)
    except ValueError:
        rel = str(target)
    return _href(rel)


def _copy_button(label: str, path: str) -> str:
    return (
        f'<button type="button" class="copy-btn" '
        f'data-path="{_e(path)}" '
        f'onclick="copyText(this.dataset.path)">{_e(label)}</button>'
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = path.parent / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    tmp = temp_dir / f".{path.name}.{uuid.uuid4().hex[:8]}.tmp"
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _ps_literal(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _write_open_shortcut(source_dir: Path) -> None:
    """Create a Windows shortcut that opens the gallery in the isolated browser."""
    if os.name != "nt" or getattr(sys, "frozen", False):
        return
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.is_file():
        pythonw = Path(sys.executable)
    helper = Path(__file__).resolve().parents[1] / "open_gallery.py"
    index = (source_dir / "index.html").resolve()
    if not helper.is_file() or not index.is_file():
        return

    edge = next(
        (
            p
            for p in (
                Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
                Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
            )
            if p.is_file()
        ),
        None,
    )
    icon = edge or pythonw
    ascii_shortcut = source_dir / "Open in Edge.lnk"
    shortcut = source_dir / "Открыть в Edge.lnk"
    arguments = f'"{helper}" "{index}"'
    script = (
        "$ws = New-Object -ComObject WScript.Shell\n"
        f"$sc = $ws.CreateShortcut({_ps_literal(ascii_shortcut)})\n"
        f"$sc.TargetPath = {_ps_literal(pythonw)}\n"
        f"$sc.Arguments = {_ps_literal(arguments)}\n"
        f"$sc.WorkingDirectory = {_ps_literal(source_dir)}\n"
        f"$sc.IconLocation = {_ps_literal(str(icon) + ',0')}\n"
        "$sc.Description = 'Open the gallery in the isolated browser'\n"
        "$sc.Save()\n"
    )
    try:
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-EncodedCommand",
                encoded,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=20,
            check=False,
        )
        # WScript.Shell cannot create a .lnk directly under a Cyrillic name on
        # this Windows locale, but renaming an existing .lnk works fine.
        if ascii_shortcut.is_file():
            os.replace(ascii_shortcut, shortcut)
    except Exception:
        pass


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
{body}
</div>
<div id="copy-toast"></div>
<dialog id="slot-dialog">
  <h3>Выбрать слот</h3>
  <div id="slot-dialog-list"></div>
  <div id="slot-dialog-new">
    <input id="slot-new-name" placeholder="Новый слот">
    <button type="button" class="slot-dialog-item" onclick="createSlotFromDialog()">Выбрать</button>
  </div>
  <button type="button" id="slot-dialog-close" onclick="closeSlotDialog()">Отмена</button>
</dialog>
<div id="viewer-overlay" aria-hidden="true">
  <button type="button" id="viewer-overlay-close" title="Закрыть">×</button>
  <iframe id="viewer-frame" title="3D-просмотр"></iframe>
</div>
<div id="image-overlay" aria-hidden="true">
  <img id="image-overlay-img" alt="">
</div>
<script>
let copyToastTimer = null;

function showCopyToast(message) {{
  const el = document.getElementById('copy-toast');
  if (!el) return;
  el.textContent = message;
  el.classList.add('show');
  if (copyToastTimer) clearTimeout(copyToastTimer);
  copyToastTimer = setTimeout(() => el.classList.remove('show'), 2200);
}}

async function copyText(path) {{
  let copied = false;
  if (navigator.clipboard && window.isSecureContext) {{
    try {{
      await navigator.clipboard.writeText(path);
      copied = true;
    }} catch (e) {{ }}
  }}
  if (!copied) {{
    try {{
      const area = document.createElement('textarea');
      area.value = path;
      area.setAttribute('readonly', '');
      area.style.position = 'fixed';
      area.style.top = '-1000px';
      document.body.appendChild(area);
      area.select();
      area.setSelectionRange(0, area.value.length);
      copied = document.execCommand('copy');
      area.remove();
    }} catch (e) {{ }}
  }}
  if (copied) {{
    showCopyToast('Скопировано: ' + path);
  }} else {{
    window.prompt('Скопируйте путь вручную:', path);
  }}
}}

function setSlot(box, name) {{
  if (!box) return;
  const value = box.querySelector('.slot-value');
  if (value) value.value = name;
  box.querySelectorAll('.slot-pill').forEach((pill) => {{
    pill.classList.toggle('active', pill.dataset.slot === name);
  }});
  const more = box.querySelector('.slot-more');
  if (!more) return;
  const first = (box.dataset.firstSlots || '').split('|').filter(Boolean);
  if (first.includes(name)) {{
    more.textContent = '⋯';
    more.classList.remove('active');
    more.title = 'Другой слот';
  }} else {{
    more.textContent = name.length > 10 ? name.slice(0, 9) + '…' : name;
    more.classList.add('active');
    more.title = name;
  }}
}}

function selectSlot(box, name) {{
  setSlot(box, name);
  closeSlotDialog();
}}

let activeSlotBox = null;

function openSlotDialog(button) {{
  const box = button.closest('.slot-box');
  if (!box) return;
  activeSlotBox = box;
  const list = document.getElementById('slot-dialog-list');
  const current = box.querySelector('.slot-value')?.value || '';
  list.innerHTML = '';
  const card = box.closest('.variant-card');
  const slicer = card ? (card.querySelector('.slicer-value')?.value || 'orca') : 'orca';
  const names = Array.from(box.querySelectorAll('.slot-pill'))
    .filter((pill) => pill.dataset.slicer === slicer)
    .map((pill) => pill.dataset.slot);
  names.forEach((name) => {{
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'slot-dialog-item' + (name === current ? ' active' : '');
    item.textContent = name;
    item.addEventListener('click', () => selectSlot(box, name));
    list.appendChild(item);
  }});
  const input = document.getElementById('slot-new-name');
  input.value = '';
  const dialog = document.getElementById('slot-dialog');
  if (dialog && dialog.showModal) dialog.showModal();
}}

function createSlotFromDialog() {{
  const input = document.getElementById('slot-new-name');
  const name = (input.value || '').trim();
  if (!name || !activeSlotBox) return;
  setSlot(activeSlotBox, name);
  closeSlotDialog();
}}

function closeSlotDialog() {{
  const dialog = document.getElementById('slot-dialog');
  if (dialog && dialog.close) dialog.close();
}}

function closeImage() {{
  const overlay = document.getElementById('image-overlay');
  const image = document.getElementById('image-overlay-img');
  if (overlay) overlay.classList.remove('show');
  if (overlay) overlay.setAttribute('aria-hidden', 'true');
  if (image) image.removeAttribute('src');
  document.body.classList.remove('image-open');
}}

function openImage(src, alt, event) {{
  if (event) event.preventDefault();
  const overlay = document.getElementById('image-overlay');
  const image = document.getElementById('image-overlay-img');
  if (!overlay || !image) return true;
  image.src = src;
  image.alt = alt || 'просмотр';
  overlay.classList.add('show');
  overlay.setAttribute('aria-hidden', 'false');
  document.body.classList.add('image-open');
  return false;
}}

function openImageClick(button, event) {{
  if (event) {{
    event.preventDefault();
    event.stopPropagation();
  }}
  return openImage(button.dataset.image, button.dataset.alt, event);
}}

function close3D() {{
  const overlay = document.getElementById('viewer-overlay');
  const frame = document.getElementById('viewer-frame');
  if (overlay) overlay.classList.remove('show');
  if (overlay) overlay.setAttribute('aria-hidden', 'true');
  if (frame) frame.removeAttribute('src');
  document.body.classList.remove('viewer-open');
}}

function embedProbe() {{
  return new Promise((resolve) => {{
    const image = new Image();
    let finished = false;
    const finish = (ok) => {{
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      resolve(ok);
    }};
    const timer = setTimeout(() => finish(false), 500);
    image.onload = () => finish(true);
    image.onerror = () => finish(false);
    image.src = 'http://127.0.0.1:8765/ping.png?t=' + Date.now();
  }});
}}

function openEmbedded3D(model) {{
  const overlay = document.getElementById('viewer-overlay');
  const frame = document.getElementById('viewer-frame');
  const tokenBox = document.getElementById('gallery-token');
  const token = tokenBox ? tokenBox.dataset.token : '';
  if (!overlay || !frame || !token) {{
    showCopyToast('Не удалось определить папку галереи');
    return false;
  }}
  overlay.classList.add('show');
  overlay.setAttribute('aria-hidden', 'false');
  document.body.classList.add('viewer-open');
  frame.removeAttribute('src');
  const url = 'http://127.0.0.1:8765/r/' + token + '/viewer.html?name=' +
    encodeURIComponent(model || '') + '&v=' + Date.now();
  const activate = () => {{ frame.src = url; }};
  embedProbe().then((ready) => {{
    if (ready) {{
      activate();
      return;
    }}
    window.location.href = 'scad-embed://ensure';
    let tries = 0;
    const timer = setInterval(() => {{
      tries += 1;
      embedProbe().then((running) => {{
        if (running) {{
          clearInterval(timer);
          activate();
        }} else if (tries >= 50) {{
          clearInterval(timer);
          close3D();
          showCopyToast('Не удалось запустить 3D-сервер');
        }}
      }});
    }}, 200);
  }});
  return false;
}}

function open3D(model, folder, alt, event) {{
  if (event) event.preventDefault();
  const served = (location.protocol === 'http:' || location.protocol === 'https:') &&
    location.pathname.indexOf('/r/') !== -1;
  if (!served) {{
    return openEmbedded3D(model);
  }}
  const overlay = document.getElementById('viewer-overlay');
  const frame = document.getElementById('viewer-frame');
  if (!overlay || !frame) return false;
  frame.src = new URL(
    'viewer.html?name=' + encodeURIComponent(model || '') +
    '&v=' + Date.now(),
    location.href
  ).href;
  overlay.classList.add('show');
  overlay.setAttribute('aria-hidden', 'false');
  document.body.classList.add('viewer-open');
  return false;
}}

const imageOverlay = document.getElementById('image-overlay');
if (imageOverlay) {{
  imageOverlay.addEventListener('click', closeImage);
}}
if (location.protocol === 'http:' || location.protocol === 'https:') {{
  const slotsLink = document.getElementById('slots-link');
  if (slotsLink) slotsLink.href = '/slots/';
}}
const viewerOverlay = document.getElementById('viewer-overlay');
if (viewerOverlay) {{
  viewerOverlay.addEventListener('click', (event) => {{
    if (event.target === viewerOverlay) close3D();
  }});
  document.getElementById('viewer-overlay-close').addEventListener('click', close3D);
}}
window.addEventListener('message', (event) => {{
  if (event.data && event.data.type === 'scad-viewer-close') close3D();
}});
document.addEventListener('keydown', (event) => {{
  if (event.key === 'Escape') {{
    close3D();
    closeImage();
  }}
}});

function setSlotSlicer(box, name) {{
  if (!box) return;
  const pills = Array.from(box.querySelectorAll('.slot-pill'));
  pills.forEach((pill) => {{
    const matches = pill.dataset.slicer === name;
    pill.hidden = !matches;
    pill.classList.remove('active');
  }});
  const names = pills.filter((pill) => pill.dataset.slicer === name).map((pill) => pill.dataset.slot);
  const value = box.querySelector('.slot-value');
  const first = names.length ? names[0] : '';
  if (value) value.value = first;
  if (first) {{
    const active = pills.find((pill) => pill.dataset.slicer === name && pill.dataset.slot === first);
    if (active) active.classList.add('active');
  }}
  const empty = box.querySelector('.slot-empty');
  if (empty) empty.hidden = names.length > 0;
  const more = box.querySelector('.slot-more');
  if (!more) return;
  if (first) {{
    more.textContent = '⋯';
    more.classList.remove('active');
    more.title = 'Другой слот';
  }} else {{
    more.textContent = '⋯';
    more.classList.remove('active');
    more.title = 'Слотов пока нет';
  }}
}}

function setSlicer(box, name) {{
  if (!box) return;
  const value = box.querySelector('.slicer-value');
  if (value) value.value = name;
  box.querySelectorAll('.slicer-pill').forEach((pill) => {{
    pill.classList.toggle('active', pill.dataset.slicer === name);
  }});
  const card = box.closest('.variant-card');
  const slotBox = card ? card.querySelector('.slot-box') : null;
  if (slotBox) setSlotSlicer(slotBox, name);
}}

function openSlicer(button) {{
  const box = button.closest('.slicer-box');
  const value = box ? box.querySelector('.slicer-value') : null;
  const name = value ? value.value : 'orca';
  window.location.href = 'scad-slicer://open?name=' + encodeURIComponent(name);
}}

let scadSourceText = null;
let scadSourceLoaded = false;
const scadKeywords = new Set(["module", "function", "if", "else", "for", "let", "include", "use", "true", "false", "undef", "echo", "assert", "children", "each", "intersection_for", "render", "linear_extrude", "rotate_extrude", "translate", "rotate", "scale", "mirror", "resize", "color", "offset", "hull", "minkowski", "union", "difference", "intersection", "import", "surface", "polygon", "polyhedron", "circle", "square", "text", "cube", "sphere", "cylinder", "$fn", "$fa", "$fs", "$t"]);

function escapeScad(value) {{
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}}

function isIdentStart(code) {{
  return (code >= 65 && code <= 90) || (code >= 97 && code <= 122) || code === 95 || code === 36;
}}

function isIdentPart(code) {{
  return isIdentStart(code) || (code >= 48 && code <= 57);
}}

function highlightScad(source) {{
  let result = "";
  let i = 0;
  while (i < source.length) {{
    if (source.startsWith("//", i)) {{
      let end = source.indexOf(String.fromCharCode(10), i);
      if (end < 0) end = source.length;
      result += '<span class="tok-com">' + escapeScad(source.slice(i, end)) + "</span>";
      i = end;
    }} else if (source.startsWith("/*", i)) {{
      let end = source.indexOf("*/", i + 2);
      end = end < 0 ? source.length : end + 2;
      result += '<span class="tok-com">' + escapeScad(source.slice(i, end)) + "</span>";
      i = end;
    }} else {{
      const code = source.charCodeAt(i);
      if (code === 34 || code === 39) {{
        const quote = code;
        let end = i + 1;
        while (end < source.length) {{
          const ch = source.charCodeAt(end);
          if (ch === 92) {{ end += 2; continue; }}
          if (ch === quote) {{ end += 1; break; }}
          end += 1;
        }}
        result += '<span class="tok-str">' + escapeScad(source.slice(i, end)) + "</span>";
        i = end;
      }} else if ((code >= 48 && code <= 57) || (code === 46 && source.charCodeAt(i + 1) >= 48 && source.charCodeAt(i + 1) <= 57)) {{
        let end = i + 1;
        while (end < source.length) {{
          const ch = source.charCodeAt(end);
          if ((ch >= 48 && ch <= 57) || ch === 46) end += 1;
          else break;
        }}
        result += '<span class="tok-num">' + escapeScad(source.slice(i, end)) + "</span>";
        i = end;
      }} else if (isIdentStart(code)) {{
        let end = i + 1;
        while (end < source.length && isIdentPart(source.charCodeAt(end))) end += 1;
        const word = source.slice(i, end);
        result += scadKeywords.has(word)
          ? '<span class="tok-kw">' + escapeScad(word) + "</span>"
          : escapeScad(word);
        i = end;
      }} else {{
        result += escapeScad(source[i]);
        i += 1;
      }}
    }}
  }}
  return result;
}}

function loadSourceCode() {{
  if (scadSourceLoaded) return;
  const code = document.getElementById("source-code");
  const panel = document.getElementById("source-panel");
  if (!code || !panel) return;
  const embedded = document.getElementById("source-embedded");
  if (embedded && embedded.textContent.trim()) {{
    scadSourceText = embedded.textContent;
    scadSourceLoaded = true;
    code.innerHTML = highlightScad(scadSourceText);
    return;
  }}
  const parts = location.pathname.split("/");
  const token = parts.length >= 3 && parts[1] === "r" ? parts[2] : "";
  const url = token ? "/source?folder=" + encodeURIComponent(token) : "/source";
  fetch(url, {{ cache: "no-store" }})
    .then(function (response) {{
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.text();
    }})
    .then(function (text) {{
      scadSourceText = text;
      scadSourceLoaded = true;
      code.innerHTML = highlightScad(text);
      const name = document.getElementById("code-source-name");
      if (name) name.textContent = panel.dataset.source || "Исходник .scad";
    }})
    .catch(function (error) {{
      code.textContent = "Не удалось загрузить код: " + error.message +
        String.fromCharCode(10) +
        "Код доступен при открытии галереи через локальный сервер.";
    }});
}}

function toggleCode() {{
  const open = document.body.classList.toggle("code-mode");
  const button = document.getElementById("code-toggle");
  if (button) {{
    button.textContent = open ? "К вариантам" : "Код";
    button.classList.toggle("active-code", open);
  }}
  if (open) loadSourceCode();
}}

function copySourceCode(button) {{
  const text = scadSourceText || "";
  const done = function (ok) {{
    if (!button) return;
    button.textContent = ok ? "Скопировано" : "Не удалось";
    setTimeout(function () {{ button.textContent = "Копировать код"; }}, 1600);
  }};
  if (navigator.clipboard && window.isSecureContext) {{
    navigator.clipboard.writeText(text).then(function () {{ done(true); }}, function () {{ done(false); }});
    return;
  }}
  try {{
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.top = "-1000px";
    document.body.appendChild(area);
    area.select();
    done(document.execCommand("copy"));
    area.remove();
  }} catch (e) {{
    done(false);
  }}
}}

function assignSlot(button) {{  const box = button.closest('.slot-box');
  if (!box) return;
  const value = box.querySelector('.slot-value');
  const slot = (value ? value.value : '').trim();
  if (!slot) {{
    openSlotDialog(button);
    showCopyToast('Сначала выбери слот');
    return;
  }}
  const stl = button.dataset.stl || '';
  if (!stl) return;
  const card = button.closest('.variant-card');
  const slicer = card ? (card.querySelector('.slicer-value')?.value || 'orca') : 'orca';
  window.location.href = 'scad-slot://assign?slot=' +
    encodeURIComponent(slot) + '&stl=' + encodeURIComponent(stl) +
    '&slicer=' + encodeURIComponent(slicer);
}}

const slotDialog = document.getElementById('slot-dialog');
if (slotDialog) {{
  slotDialog.addEventListener('click', (event) => {{
    const rect = slotDialog.getBoundingClientRect();
    const inside = event.clientX >= rect.left && event.clientX <= rect.right &&
      event.clientY >= rect.top && event.clientY <= rect.bottom;
    if (!inside) closeSlotDialog();
  }});
}}
if (new URLSearchParams(location.search).get('code') === '1') toggleCode();
if (new URLSearchParams(location.search).get('viewer') === '1') {{
  const first3d = document.querySelector('.thumb.viewer-link');
  if (first3d) first3d.click();
}}
</script>
</body>
</html>
"""


def _status_badge(status: str) -> str:
    status = (status or "ok").lower()
    label = {"ok": "готово", "partial": "частично", "error": "ошибка"}.get(status, status)
    cls = status if status in {"ok", "partial", "error"} else "error"
    return f'<span class="badge {cls}">{_e(label)}</span>'


def _unique_variants(variants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return one entry per rendered result.

    Aliases share the same image/geometry but have different switch values.
    They must not produce duplicate cards with identical photos.
    """
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for variant in variants:
        image = variant.get("image")
        geometry = variant.get("geometry")
        stl = variant.get("stl")
        if image:
            key = f"image:{image}"
        elif geometry or stl:
            key = f"geometry:{geometry or ''}|stl:{stl or ''}"
        else:
            key = f"id:{variant.get('id', '')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(variant)
    return unique


def _image_exists(source_dir: Path, variant: dict[str, Any]) -> bool:
    image = variant.get("image")
    return bool(image) and (source_dir / image).is_file()


def _variant_card(
    source_dir: Path,
    variant: dict[str, Any],
    slots_by_slicer: dict[str, dict[str, Any]] | None = None,
) -> str:
    label = variant.get("label") or "по умолчанию"
    stamp = variant.get("rendered_at") or ""
    image = variant.get("image")
    stl = variant.get("stl")
    copy_path_button = ""
    if image and (source_dir / image).is_file():
        thumb = (
            '<div class="thumb-wrap">'
            f'<a class="thumb viewer-link" href="{_href(image)}" '
            f'data-model="{_e(stl)}" '
            f'data-folder="{_e(str(source_dir.resolve()))}" '
            f'data-alt="{_e(label)}" title="Открыть 3D" '
            f'onclick="return open3D(this.dataset.model, this.dataset.folder, '
            f'this.dataset.alt, event)">'
            f'<img src="{_href(image)}" alt="{_e(label)}" loading="lazy"></a>'
            f'<button type="button" class="thumb-expand" '
            f'data-image="{_e(_href(image))}" data-alt="{_e(label)}" '
            f'title="Открыть изображение" '
            f'onclick="return openImageClick(this, event)">'
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<polyline points="9 4 4 4 4 9"></polyline>'
            '<polyline points="15 4 20 4 20 9"></polyline>'
            '<polyline points="4 15 4 20 9 20"></polyline>'
            '<polyline points="20 15 20 20 15 20"></polyline>'
            '</svg></button></div>'
        )
        copy_path_button = (
            f'<button type="button" class="copy-path" '
            f'data-path="{_e(str((source_dir / image).resolve()))}" '
            f'onclick="copyText(this.dataset.path)">Скопировать полный путь к изображению</button>'
        )
    else:
        thumb = '<div class="thumb" style="height:240px;display:grid;place-items:center;color:#94a3b8">нет изображения</div>'
        copy_path_button = ""
    copy_stl_button = ""
    if stl and (source_dir / stl).is_file():
        copy_stl_button = (
            f'<button type="button" class="copy-path" '
            f'data-path="{_e(str((source_dir / stl).resolve()))}" '
            f'onclick="copyText(this.dataset.path)">Скопировать полный путь к STL</button>'
        )
    slots_by_slicer = slots_by_slicer or {}
    default_slicer = next(
        (slicer for slicer in SLICER_LABELS if slots_by_slicer.get(slicer)),
        "orca",
    )
    default_slot = next(iter(slots_by_slicer.get(default_slicer, {})), "")
    slot_box = ""
    if stl and (source_dir / stl).is_file():
        pill_parts: list[str] = []
        for slicer, label in SLICER_LABELS.items():
            for name in slots_by_slicer.get(slicer, {}):
                active = slicer == default_slicer and name == default_slot
                hidden = "" if slicer == default_slicer else " hidden"
                pill_parts.append(
                    f'<button type="button" class="slot-pill{" active" if active else ""}" '
                    f'data-slicer="{_e(slicer)}" data-slot="{_e(name)}"{hidden} '
                    f'onclick="selectSlot(this.closest(\'.slot-box\'), this.dataset.slot)">'
                    f'{_e(name)}</button>'
                )
        pills = "".join(pill_parts)
        empty = (
            '<span class="slot-empty">Слотов пока нет</span>'
            if not pills
            else '<span class="slot-empty" hidden>Слотов пока нет</span>'
        )
        slot_box = (
            f'<div class="slot-box" data-default-slot="{_e(default_slot)}">'
            f'<div class="slot-pills">{pills}{empty}'
            f'<button type="button" class="slot-more" title="Другой слот" '
            f'onclick="openSlotDialog(this)">⋯</button>'
            f'<input type="hidden" class="slot-value" value="{_e(default_slot)}">'
            '</div>'
            f'<button type="button" class="slot-send" '
            f'data-stl="{_e(str((source_dir / stl).resolve()))}" '
            f'onclick="assignSlot(this)">Отправить в слот</button>'
            '</div>'
        )
    slicer_parts = "".join(
        f'<button type="button" class="slicer-pill{" active" if slicer == default_slicer else ""}" '
        f'data-slicer="{_e(slicer)}" '
        f'onclick="setSlicer(this.closest(\'.slicer-box\'), \'{_e(slicer)}\')">'
        f'{_e(label)}</button>'
        for slicer, label in SLICER_LABELS.items()
    )
    slicer_box = (
        '<div class="slicer-box">'
        f'<div class="slicer-pills">{slicer_parts}'
        f'<input type="hidden" class="slicer-value" value="{_e(default_slicer)}">'
        '</div>'
        '<button type="button" class="open-slicer" '
        'onclick="openSlicer(this)">Открыть слайсер</button>'
        '</div>'
    )
    notes: list[str] = []
    if variant.get("alias_of"):
        notes.append(
            f'<div class="meta-row"><span class="chip">та же геометрия: '
            f'{_e(variant.get("alias_of"))}</span></div>'
        )
    aliases = [str(item) for item in (variant.get("aliases") or []) if item]
    if aliases:
        notes.append(
            f'<div class="meta-row"><span class="chip">ещё '
            f'{_ru(len(aliases), "комбинация", "комбинации", "комбинаций")} '
            f'с той же геометрией</span></div>'
        )
    if stamp:
        notes.append(f'<div class="stamp">обновлено {_e(_format_dt(stamp))}</div>')
    if variant.get("status") == "error":
        notes.append(
            f'<div class="stale">последний рендер не удался: '
            f'{_e(variant.get("error") or "unknown error")}</div>'
        )

    return f"""<article class="card variant-card">
{thumb}
{slot_box}
{slicer_box}
{copy_path_button}
{copy_stl_button}
<div class="body">
<p class="label">{_e(label)}</p>
{''.join(notes)}
</div>
</article>"""


def write_source_page(
    source_dir: Path,
    manifest: dict[str, Any],
    contact_name: str | None = None,
) -> None:
    source = manifest.get("source") or {}
    source_abs = Path(source.get("abs", ""))
    source_rel = source.get("rel", source_abs.name)
    title = Path(str(source_rel)).stem
    all_variants = manifest.get("variants") or []
    variants = _unique_variants(all_variants)
    total_variants = len(all_variants)
    switches = manifest.get("switches") or []
    status = manifest.get("status", "ok")

    switch_html = ""
    if switches:
        rows = []
        for sw in switches:
            default_value = str(sw.get("default", ""))
            opts = " ".join(
                f'<span class="chip">{_e(o)}</span>'
                for o in sw.get("options", [])
                if str(o) != default_value
            )
            rows.append(
                f'<div class="switch"><span class="name">{_e(sw.get("name"))}</span>'
                f'<span class="chip">default: <b>{_e(sw.get("default"))}</b></span>'
                f'{opts}</div>'
            )
        switch_html = '<div class="switches">' + "".join(rows) + "</div>"
    else:
        switch_html = (
            '<div class="switches"><div class="switch">'
            '<span class="chip">строковых переключателей нет — один вариант</span>'
            "</div></div>"
        )

    error = manifest.get("error")
    notice = ""
    if error:
        notice = f'<div class="notice bad"><b>Ошибка анализа/рендера.</b><br>{_e(error)}</div>'
    elif status == "partial":
        notice = (
            '<div class="notice warn">Часть вариантов не отрендерилась. '
            "Подробности — в manifest.json.</div>"
        )

    write_slots_page()
    slots_by_slicer = load_all_slots()
    cards = "".join(
        _variant_card(source_dir, v, slots_by_slicer) for v in variants
    )
    if not cards:
        cards = '<div class="empty">Вариантов пока нет.</div>'
    stl_count = len(
        {
            str(v["stl"])
            for v in variants
            if v.get("stl") and (source_dir / str(v["stl"])).is_file()
        }
    )

    contact_link = ""
    if contact_name and (source_dir / contact_name).is_file():
        contact_link = (
            f'<a class="btn" style="border-color:#0f766e;color:#0f766e" '
            f'href="{_href(contact_name)}" target="_blank">Контактный лист</a>'
        )
    src_href = _rel_link(source_abs, source_dir)
    try:
        source_text = source_abs.read_text(encoding="utf-8", errors="replace")
    except OSError:
        source_text = ""
    updated = manifest.get("updated_at", "")
    folder_path = source_dir.resolve()
    folder_abs = str(folder_path)
    folder_uri = folder_path.as_uri().rstrip("/") + "/"
    folder_actions = (
        f'<a id="slots-link" class="btn" style="border-color:#0f766e;color:#0f766e" '
        f'href="{_e(slots_page_path().resolve().as_uri())}" target="_blank" '
        f'rel="noopener">Слоты слайсеров</a>'
        f'<a class="btn" style="border-color:#0f766e;color:#0f766e" '
        f'href="{_e(folder_uri)}" target="_blank" rel="noopener">Открыть папку</a>'
        + _copy_button("Копировать папку", folder_abs)
    )

    body = f"""
<div id="gallery-token" data-token="{_e(base64.urlsafe_b64encode(str(folder_path).encode('utf-8')).decode('ascii').rstrip('='))}" hidden></div>
<div class="toolbar">
  <div class="crumbs">{_e(source_rel)}</div>
  <div><button id="code-toggle" class="btn" style="border-color:#cbd5e1;color:#334155;background:#fff" onclick="toggleCode()">Код</button>{folder_actions}{contact_link}<button class="btn" style="border-color:#cbd5e1;color:#334155;background:#fff" onclick="location.reload()">Обновить</button></div>
</div>
<header class="source-head">
  <h1>{_e(title)}</h1>
  <div class="sub"><a href="{src_href}">{_e(source_rel)}</a> · обновлено {_e(_format_dt(updated))}</div>
  <div class="meta-row">{_status_badge(status)}<span class="chip">вариантов: {len(variants)}</span>{f'<span class="chip">комбинаций: {total_variants}</span>' if total_variants != len(variants) else ''}{f'<span class="chip">STL: {stl_count}</span>' if stl_count else ''}</div>
  {switch_html}
  {notice}
</header>
<section class="project" style="margin-top:26px">
  <div class="grid">{cards}</div>
</section>
<aside id="source-panel" data-source="{_e(source_rel)}">
  <div class="code-head">
    <span class="code-name" id="code-source-name">{_e(source_rel)}</span>
    <button type="button" onclick="copySourceCode(this)">Копировать код</button>
    <button type="button" onclick="toggleCode()">Свернуть</button>
  </div>
  <pre id="source-embedded" hidden>{_e(source_text)}</pre>
  <pre id="source-code">Загрузка…</pre>
</aside>
<div class="footer">Сгенерировано scad-variants. Рендер: OpenSCAD.</div>
"""
    _write(source_dir / "index.html", _page(f"{title} — варианты", body))
    _write_open_shortcut(source_dir)


def _load_manifest(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _global_card(manifest_path: Path, output_root: Path, manifest: dict[str, Any]) -> str:
    source_dir = manifest_path.parent
    source = manifest.get("source") or {}
    rel = str(source.get("rel", source_dir.name))
    variants = _unique_variants(manifest.get("variants") or [])
    status = manifest.get("status", "ok")
    stem = Path(rel).stem
    page = source_dir / "index.html"
    page_href = _rel_link(page, output_root)

    contact = source_dir / "contact.png"
    thumb_path: Path | None = None
    for variant in variants:
        image = variant.get("image")
        if image and (source_dir / image).is_file():
            thumb_path = source_dir / image
            break
    if thumb_path is None and contact.is_file():
        thumb_path = contact
    if thumb_path is not None:
        thumb = (
            f'<a class="thumb" href="{page_href}"><img src="{_rel_link(thumb_path, output_root)}" '
            f'alt="{_e(stem)}" loading="lazy"></a>'
        )
    else:
        thumb = (
            '<a class="thumb" href="' + page_href + '"><div style="height:240px;'
            'display:grid;place-items:center;color:#94a3b8">нет изображения</div></a>'
        )

    switches = manifest.get("switches") or []
    chip_bits = []
    for sw in switches[:3]:
        chip_bits.append(
            f'<span class="chip"><b>{_e(sw.get("name"))}</b>: '
            f'{_e(", ".join(map(str, sw.get("options", []))))}</span>'
        )
    if not chip_bits:
        chip_bits.append('<span class="chip">без переключателей</span>')
    updated = manifest.get("updated_at", "")
    return f"""<article class="card">
{thumb}
<div class="body">
<h3><a href="{page_href}">{_e(stem)}</a></h3>
<div class="path">{_e(rel)}</div>
<div class="meta-row">{_status_badge(status)}<span class="chip">{len(variants)} вар.</span>{''.join(chip_bits)}</div>
<div class="stamp" style="color:#64748b;font-size:12px;margin-top:8px">обновлено {_e(_format_dt(updated))}</div>
</div>
</article>"""


def write_global_index(output_root: Path) -> int:
    manifests: list[tuple[Path, dict[str, Any]]] = []
    if output_root.is_dir():
        for path in sorted(output_root.rglob("manifest.json")):
            if "node_modules" in path.parts:
                continue
            manifest = _load_manifest(path)
            if not manifest:
                continue
            source = manifest.get("source") or {}
            source_abs = Path(str(source.get("abs", "")))
            if source_abs and not source_abs.exists():
                continue
            manifests.append((path, manifest))

    groups: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    for path, manifest in manifests:
        rel = str((manifest.get("source") or {}).get("rel", ""))
        parts = rel.replace("\\", "/").split("/")
        project = parts[0] if len(parts) > 1 else "Корень"
        groups.setdefault(project, []).append((path, manifest))

    total_variants = sum(
        len(_unique_variants(m.get("variants") or [])) for _, m in manifests
    )
    total_stl = sum(
        len(
            {
                str(variant["stl"])
                for variant in _unique_variants(manifest.get("variants") or [])
                if variant.get("stl")
                and (path.parent / str(variant["stl"])).is_file()
            }
        )
        for path, manifest in manifests
    )
    generated = datetime.now().astimezone().isoformat(timespec="seconds")
    sections = []
    for project in sorted(groups):
        items = groups[project]
        cards = "".join(_global_card(p, output_root, m) for p, m in items)
        sections.append(
            f'<section class="project"><h2>{_e(project)}'
            f'<span>{_ru(len(items), "файл", "файла", "файлов")}</span></h2>'
            f'<div class="grid">{cards}</div></section>'
        )
    if not sections:
        sections.append(
            '<div class="empty" style="margin-top:28px">Пока нет отрендеренных '
            'SCAD-файлов. Положите .scad в отслеживаемую папку.</div>'
        )

    body = f"""
<header class="hero">
  <div>
    <h1>Варианты OpenSCAD</h1>
    <p>Автоматические превью строковых переключателей и STL для печатаемых
    вариантов. Числовые параметры не размножаются; перерендериваются только
    варианты, у которых изменился код.</p>
    <div style="margin-top:16px"><button class="btn" onclick="location.reload()">Обновить страницу</button></div>
  </div>
  <div class="meta">{_ru(len(manifests), "файл", "файла", "файлов")} · {_ru(total_variants, "вариант", "варианта", "вариантов")} · {total_stl} STL<br>{_e(_format_dt(generated))}</div>
</header>
{''.join(sections)}
<div class="footer">Папка результатов: {_e(output_root.name)}. Страница обновляется
после каждого цикла рендера.</div>
"""
    _write(output_root / "index.html", _page("Варианты OpenSCAD", body))
    return len(manifests)
