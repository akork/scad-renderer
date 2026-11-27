"""Windows per-user installer embedded in SCADRenderer.exe."""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import winreg
from pathlib import Path

from .paths import app_root

TARGET = Path(
    os.environ.get("SCAD_INSTALL_TARGET")
    or (Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Programs" / "SCADRenderer")
)
TASK_NAME = "SCAD Render Tray"
CONTEXT_KEY = r"Software\Classes\SystemFileAssociations\.scad\shell\SCADRender"
PROTOCOLS = {
    "scad-viewer": "viewer",
    "scad-gallery": "gallery",
    "scad-slot": "slot",
    "scad-slicer": "slicer",
    "scad-embed": "ensure",
}
START_MENU = (
    Path(os.environ.get("APPDATA", Path.home()))
    / "Microsoft"
    / "Windows"
    / "Start Menu"
    / "Programs"
    / "SCAD Render.lnk"
)
POWERSHELL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / (
    "System32/WindowsPowerShell/v1.0/powershell.exe"
)


def _ps_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _run_ps(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            str(POWERSHELL),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _show(message: str, *, error: bool = False) -> None:
    try:
        flags = 0x10 if error else 0x40
        ctypes.windll.user32.MessageBoxW(None, message, "SCAD Renderer", flags)
    except Exception:
        pass


def _log(message: str) -> None:
    try:
        path = Path(os.environ.get("TEMP", str(Path.home()))) / "scad-install.log"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")
    except OSError:
        pass


def _stop_old(target: Path) -> None:
    escaped = str(target).replace("'", "''")
    script = f"""
$target = '{escaped}'
$self = {os.getpid()}
Get-CimInstance Win32_Process -Filter "Name = 'SCADRenderer.exe'" -ErrorAction SilentlyContinue |
  Where-Object {{ $_.CommandLine -match [regex]::Escape($target) -and $_.ProcessId -ne $self }} |
  ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}
Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" -ErrorAction SilentlyContinue |
  Where-Object {{ $_.CommandLine -match 'tray-host\\.ps1|scad-tray\\.ps1' -and $_.CommandLine -match [regex]::Escape($target) -and $_.ProcessId -ne $PID }} |
  ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}
"""
    try:
        _run_ps(script)
    except Exception as exc:
        _log(f"stop old failed: {exc}")


def _set_value(root, path: str, name: str | None, value: str) -> None:
    key = winreg.CreateKey(root, path)
    try:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
    finally:
        winreg.CloseKey(key)


def _delete_tree(root, path: str) -> None:
    try:
        key = winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS)
    except OSError:
        return
    try:
        while True:
            try:
                child = winreg.EnumKey(key, 0)
            except OSError:
                break
            _delete_tree(root, path + "\\" + child)
    finally:
        winreg.CloseKey(key)
    try:
        winreg.DeleteKey(root, path)
    except OSError:
        pass


def _register_shell(target: Path) -> None:
    exe = target / "SCADRenderer.exe"
    _set_value(
        winreg.HKEY_CURRENT_USER,
        CONTEXT_KEY,
        None,
        "Отрендерить SCAD (PNG + STL)",
    )
    _set_value(
        winreg.HKEY_CURRENT_USER,
        CONTEXT_KEY + "\\command",
        None,
        f'"{exe}" render-file "%1"',
    )

    for protocol, mode in PROTOCOLS.items():
        base = "Software\\Classes\\" + protocol
        _set_value(winreg.HKEY_CURRENT_USER, base, None, "URL:SCAD " + protocol)
        _set_value(winreg.HKEY_CURRENT_USER, base, "URL Protocol", "")
        _set_value(
            winreg.HKEY_CURRENT_USER,
            base + "\\shell\\open\\command",
            None,
            f'"{exe}" {mode} "%1"',
        )

    openscad = shutil.which("openscad")
    if openscad:
        _set_value(
            winreg.HKEY_CURRENT_USER,
            CONTEXT_KEY,
            "Icon",
            openscad + ",0",
        )


def _unregister_shell() -> None:
    _delete_tree(winreg.HKEY_CURRENT_USER, CONTEXT_KEY)
    for protocol in PROTOCOLS:
        _delete_tree(winreg.HKEY_CURRENT_USER, "Software\\Classes\\" + protocol)
    try:
        START_MENU.unlink()
    except OSError:
        pass


def _register_startup(target: Path) -> None:
    tray = target / "tray"
    script = f"""
$target = {_ps_quote(str(target))}
$tray = {_ps_quote(str(tray))}
$action = New-ScheduledTaskAction -Execute "$env:SystemRoot\\System32\\wscript.exe" -Argument ('"' + (Join-Path $tray 'tray-launch.vbs') + '"') -WorkingDirectory $tray
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\\$env:USERNAME"
$trigger.Delay = 'PT15S'
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut({_ps_quote(str(START_MENU))})
$lnk.TargetPath = "$env:SystemRoot\\System32\\wscript.exe"
$lnk.Arguments = '"' + (Join-Path $tray 'tray-launch.vbs') + '"'
$lnk.WorkingDirectory = $tray
$lnk.IconLocation = "$env:SystemRoot\\System32\\shell32.dll,3"
$lnk.Description = 'SCAD Render'
$lnk.Save()
Start-ScheduledTask -TaskName '{TASK_NAME}'
"""
    result = _run_ps(script)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "task registration failed").strip())


def _unregister_startup() -> None:
    _run_ps(
        f"Unregister-ScheduledTask -TaskName '{TASK_NAME}' -Confirm:$false -ErrorAction SilentlyContinue"
    )


def install(*, quiet: bool = False) -> int:
    source = app_root()
    _log(f"install start source={source} target={TARGET} self={os.getpid()}")
    if source != TARGET:
        TARGET.mkdir(parents=True, exist_ok=True)
        _stop_old(TARGET)
        _log("stop old done")
        shutil.copytree(source, TARGET, dirs_exist_ok=True)
        _log("copy done")
    else:
        _stop_old(TARGET)
        _log("stop old done (in place)")

    exe = TARGET / "SCADRenderer.exe"
    if not exe.is_file():
        message = f"Не найден {exe}"
        _log(message)
        if not quiet:
            _show(message, error=True)
        return 1

    try:
        _register_shell(TARGET)
        _log("registry done")
        _register_startup(TARGET)
        _log("startup done")
    except Exception as exc:
        _log(f"install failed: {exc}")
        if not quiet:
            _show(f"Установка не завершена:\n\n{exc}", error=True)
        return 1

    if not quiet:
        _show(
            f"SCAD Renderer установлен:\n\n{TARGET}\n\n"
            "Контекстное меню, протоколы и автозапуск настроены."
        )
    _log("install complete")
    return 0


def uninstall(*, quiet: bool = False) -> int:
    _stop_old(TARGET)
    _unregister_startup()
    _unregister_shell()
    if TARGET.is_dir():
        shutil.rmtree(TARGET, ignore_errors=True)
    if not quiet:
        _show("SCAD Renderer удалён.\n\nСлоты в slicer-slots сохранены.")
    return 0
