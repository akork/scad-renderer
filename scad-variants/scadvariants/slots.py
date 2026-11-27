"""Stable Orca slots.

An Orca object can be loaded once from a slot file and then reloaded from disk
when the slot is assigned a new STL.  Each slot has its own stable path, so a
plate with several different objects simply uses several slots.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

PROJECT_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = PROJECT_DIR.parent
SLOTS_DIR = WORKSPACE_DIR / "orca-slots"
SLOTS_JSON = SLOTS_DIR / "slots.json"
SLOTS_PAGE = SLOTS_DIR / "index.html"

SLOT_NAME_RE = re.compile(r'^[^<>:"/\\|?*\x00-\x1f]{1,40}$')
RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _e(value: Any) -> str:
    import html

    return html.escape(str(value), quote=True)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _format_dt(value: Any) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%d.%m.%Y %H:%M")
    except (ValueError, TypeError):
        return str(value or "")


def allowed_path(path: Path) -> bool:
    roots = [
        (Path.home() / "Downloads").resolve(),
        WORKSPACE_DIR.resolve(),
    ]
    resolved = path.resolve()
    return any(resolved == root or root in resolved.parents for root in roots)


def validate_name(name: str) -> str:
    name = str(name or "").strip()
    if not name or name in {".", "..", "__new__"} or name.upper() in RESERVED_NAMES:
        raise ValueError("Недопустимое имя слота")
    if not SLOT_NAME_RE.fullmatch(name):
        raise ValueError("В имени слота есть недопустимые символы")
    if name.endswith(".") or name.endswith(" "):
        raise ValueError("Имя слота не должно заканчиваться точкой или пробелом")
    return name


def slot_file(name: str) -> Path:
    return SLOTS_DIR / f"{name}.stl"


def load_slots() -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(SLOTS_JSON.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    slots = data.get("slots") if isinstance(data, dict) else None
    return {
        str(name): value
        for name, value in (slots or {}).items()
        if isinstance(value, dict)
    }


def _save_slots(slots: dict[str, dict[str, Any]]) -> None:
    SLOTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "slots": slots}
    tmp = SLOTS_JSON.with_name(f".{SLOTS_JSON.name}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, SLOTS_JSON)


def _refresh_gallery(source_dir: Path) -> None:
    try:
        manifest_path = source_dir / "manifest.json"
        if not manifest_path.is_file():
            return
        import json

        from .gallery import write_source_page

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        contact = source_dir / "contact.png"
        write_source_page(
            source_dir,
            manifest,
            contact.name if contact.is_file() else None,
        )
    except Exception:
        pass


def assign_slot(name: str, stl: Path) -> Path:
    """Copy an STL to a stable slot path and update the slot registry."""
    name = validate_name(name)
    stl = Path(stl).expanduser().resolve()
    if stl.suffix.lower() != ".stl" or not stl.is_file():
        raise ValueError(f"STL не найден: {stl}")
    if not allowed_path(stl):
        raise ValueError(f"STL вне разрешённых папок: {stl}")

    SLOTS_DIR.mkdir(parents=True, exist_ok=True)
    target = slot_file(name)
    temp = SLOTS_DIR / f".{name}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        shutil.copy2(stl, temp)
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)

    slots = load_slots()
    slots[name] = {
        "name": name,
        "file": target.name,
        "path": str(target),
        "source_stl": str(stl),
        "source_dir": str(stl.parent),
        "updated_at": _now(),
    }
    _save_slots(slots)
    write_slots_page()
    # Rebuild the gallery the STL came from so the new slot appears in its
    # selector without waiting for the next render.
    _refresh_gallery(stl.parent)
    return target


def delete_slot(name: str) -> Path:
    """Delete a slot file and its registry entry."""
    name = validate_name(name)
    slots = load_slots()
    item = slots.pop(name, None)
    if item is None:
        raise ValueError(f"Слот не найден: {name}")
    path = Path(str(item.get("path") or slot_file(name)))
    source_dir = Path(str(item.get("source_dir") or ""))
    if path.is_file():
        path.unlink()
    _save_slots(slots)
    write_slots_page()
    if source_dir.is_dir():
        _refresh_gallery(source_dir)
    return path


def write_slots_page() -> None:
    slots = load_slots()
    rows: list[str] = []
    for name in sorted(slots, key=str.casefold):
        item = slots[name]
        path = str(item.get("path") or slot_file(name))
        source = str(item.get("source_stl") or "")
        rows.append(
            f'<tr><td><b>{_e(name)}</b></td>'
            f'<td><div class="path">{_e(path)}</div>'
            f'<div class="src">{_e(source)}</div></td>'
            f'<td class="nowrap">{_e(_format_dt(item.get("updated_at")))}</td>'
            f'<td><div class="actions">'
            f'<button type="button" class="copy" '
            f'data-path="{_e(path)}" onclick="copyText(this.dataset.path)">'
            f'Скопировать путь</button>'
            f'<button type="button" class="del" data-slot="{_e(name)}" '
            f'onclick="deleteSlot(this.dataset.slot)">Удалить</button>'
            f'</div></td></tr>'
        )
    table = (
        '<table><thead><tr><th>Слот</th><th>Файл</th><th>Обновлён</th>'
        '<th></th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
        if rows
        else '<div class="empty">Слотов пока нет. Создай первый слот из карточки '
        "галереи: выбери «+ новый слот…».</div>"
    )
    html = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Слоты Orca</title>
<style>
:root {{ --line:#e2e8f0; --muted:#64748b; --accent:#0f766e; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#f4f6f9; color:#111827; font-family:"Segoe UI",system-ui,sans-serif; }}
.wrap {{ max-width:1100px; margin:0 auto; padding:30px 28px 70px; }}
h1 {{ font-size:26px; margin:0 0 8px; }}
.sub {{ color:var(--muted); font-size:13px; margin-bottom:22px; line-height:1.5; }}
.panel {{ background:#fff; border:1px solid var(--line); border-radius:14px; overflow:hidden; }}
table {{ width:100%; border-collapse:collapse; }}
th,td {{ padding:12px 14px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; font-size:13px; }}
th {{ background:#f8fafc; color:var(--muted); font-size:12px; }}
tr:last-child td {{ border-bottom:0; }}
.path {{ font-family:Consolas,monospace; font-size:12px; word-break:break-all; }}
.src {{ color:var(--muted); font-size:11px; margin-top:4px; word-break:break-all; }}
.nowrap {{ white-space:nowrap; color:var(--muted); }}
.copy {{ border:1px solid #99f6e4; background:#f0fdfa; color:var(--accent); border-radius:8px; padding:7px 10px; font:inherit; font-size:12px; font-weight:700; cursor:pointer; }}
.copy:hover {{ background:#ccfbf1; }}
.actions {{ display:flex; flex-wrap:wrap; gap:6px; }}
.del {{ border:1px solid #fecaca; background:#fef2f2; color:#b91c1c; border-radius:8px; padding:7px 10px; font:inherit; font-size:12px; font-weight:700; cursor:pointer; }}
.del:hover {{ background:#fee2e2; }}
.empty {{ padding:24px; color:var(--muted); }}
#toast {{ position:fixed; left:50%; bottom:24px; transform:translateX(-50%); background:#0f172a; color:#fff; padding:10px 14px; border-radius:9px; font-size:13px; opacity:0; pointer-events:none; transition:opacity .15s; }}
#toast.show {{ opacity:1; }}
</style></head><body><div class="wrap">
<h1>Слоты Orca</h1>
<div class="sub">Один слот = один стабильный STL. Загрузи его в объект Orca один раз;
после обновления слота выбери в Orca <b>Reload from disk</b>.<br>
Для нескольких объектов на столе используй несколько слотов.</div>
<div class="panel">{table}</div>
<div id="toast"></div>
<script>
let timer=null;
function copyText(path) {{
  const done = (ok) => {{
    const el=document.getElementById('toast');
    el.textContent = ok ? 'Скопировано: '+path : 'Не удалось скопировать';
    el.classList.add('show');
    clearTimeout(timer); timer=setTimeout(()=>el.classList.remove('show'),2200);
  }};
  if (navigator.clipboard && window.isSecureContext) {{
    navigator.clipboard.writeText(path).then(()=>done(true)).catch(()=>fallback(path,done));
  }} else {{ fallback(path,done); }}
}}
function fallback(path,done) {{
  try {{
    const a=document.createElement('textarea'); a.value=path; a.style.position='fixed'; a.style.top='-1000px';
    document.body.appendChild(a); a.select(); const ok=document.execCommand('copy'); a.remove(); done(ok);
  }} catch(e) {{ done(false); }}
}}
function deleteSlot(name) {{
  if (!confirm('Удалить слот «' + name + '»? Объект в Orca потеряет источник для Reload.')) return;
  window.location.href = 'scad-slot://delete?slot=' + encodeURIComponent(name);
}}
</script></body></html>"""
    SLOTS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SLOTS_PAGE.with_name(f".{SLOTS_PAGE.name}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(html, encoding="utf-8")
    os.replace(tmp, SLOTS_PAGE)
