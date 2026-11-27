#Requires -Version 5.1
$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$dropDir = [System.IO.Path]::GetFullPath((Join-Path $here '..\scad-drop'))
$launcher = Join-Path $dropDir 'tray-launch.vbs'
$wscript = Join-Path $env:SystemRoot 'System32\wscript.exe'

if (-not (Test-Path -LiteralPath $launcher)) {
    throw "Не найден tray-launch.vbs: $launcher"
}

$openscad = $null
$command = Get-Command 'openscad.exe' -ErrorAction SilentlyContinue
if ($command) {
    $openscad = $command.Source
} elseif (Test-Path 'C:\Users\ak\scoop\shims\openscad.exe') {
    $openscad = 'C:\Users\ak\scoop\shims\openscad.exe'
}

$programs = [Environment]::GetFolderPath('Programs')
$lnk = Join-Path $programs 'SCAD Render.lnk'
if (Test-Path -LiteralPath $lnk) {
    Remove-Item -LiteralPath $lnk -Force
}
$ws = New-Object -ComObject WScript.Shell
$shortcut = $ws.CreateShortcut($lnk)
$shortcut.TargetPath = $wscript
$shortcut.Arguments = '"' + $launcher + '"'
$shortcut.WorkingDirectory = $dropDir
$shortcut.Description = 'SCAD Render — трей и недавние рендеры'
if ($openscad) {
    $shortcut.IconLocation = ($openscad + ',0')
}
$shortcut.Save()

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

namespace ScadToast {
    [StructLayout(LayoutKind.Sequential)]
    public struct PROPERTYKEY {
        public Guid fmtid;
        public uint pid;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct PROPVARIANT {
        public ushort vt;
        public ushort r1;
        public ushort r2;
        public ushort r3;
        public IntPtr p;
    }

    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IPropertyStore {
        [PreserveSig] int GetCount(out uint cProps);
        [PreserveSig] int GetAt(uint iProp, out PROPERTYKEY pkey);
        [PreserveSig] int GetValue(ref PROPERTYKEY key, out PROPVARIANT pv);
        [PreserveSig] int SetValue(ref PROPERTYKEY key, ref PROPVARIANT pv);
        [PreserveSig] int Commit();
    }

    public static class Helper {
        [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = true)]
        static extern int SHGetPropertyStoreFromParsingName(string path, IntPtr pbc, uint flags, ref Guid riid, [MarshalAs(UnmanagedType.Interface)] out IPropertyStore store);

        [DllImport("ole32.dll", PreserveSig = true)]
        static extern int PropVariantClear(ref PROPVARIANT pv);

        public static void SetAumid(string lnkPath, string aumid) {
            Guid iid = new Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99");
            IPropertyStore store;
            int hr = SHGetPropertyStoreFromParsingName(lnkPath, IntPtr.Zero, 2, ref iid, out store);
            if (hr != 0) throw new COMException("SHGetPropertyStoreFromParsingName", hr);
            var key = new PROPERTYKEY { fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), pid = 5 };
            var pv = new PROPVARIANT { vt = 31, p = Marshal.StringToCoTaskMemUni(aumid) };
            try {
                hr = store.SetValue(ref key, ref pv);
                if (hr != 0) throw new COMException("SetValue", hr);
                hr = store.Commit();
                if (hr != 0) throw new COMException("Commit", hr);
            } finally {
                PropVariantClear(ref pv);
                Marshal.ReleaseComObject(store);
            }
        }
    }
}
'@

[ScadToast.Helper]::SetAumid($lnk, 'ScadDrop.Render')

$shell = New-Object -ComObject Shell.Application
$folder = $shell.Namespace($programs)
$item = $folder.ParseName('SCAD Render.lnk')
$aumid = $item.ExtendedProperty('System.AppUserModel.ID')

Write-Host "Ярлык уведомлений установлен:"
Write-Host "  $lnk"
Write-Host "  AUMID: $aumid"

$toast = Join-Path $here 'scadvariants\show-toast.ps1'
if (Test-Path -LiteralPath $toast) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $toast `
        -Title 'SCAD Render' `
        -Body 'Уведомления о рендеринге включены.' `
        -Aumid 'ScadDrop.Render'
}
