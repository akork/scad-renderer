param(
    [string]$Downloads = '',
    [string]$ScadRoot = '',
    [string]$StateDir = '',
    [string]$InstanceName = 'ScadDropTray',
    [int]$StartDelay = 0,
    [switch]$SelfTest,
    [switch]$SelfTestRestart,
    [string]$SelfTestOpen = ''
)

if ($StartDelay -gt 0) {
    Start-Sleep -Seconds $StartDelay
}

$ErrorActionPreference = 'Stop'
if (-not $Downloads) { $Downloads = Join-Path $env:USERPROFILE 'Downloads' }
if (-not $ScadRoot) { $ScadRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'SCAD' }
if (-not $StateDir) { $StateDir = Join-Path $PSScriptRoot 'state' }
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$script:Downloads = [IO.Path]::GetFullPath($Downloads)
$script:ScadRoot = [IO.Path]::GetFullPath($ScadRoot)
$script:StateDir = [IO.Path]::GetFullPath($StateDir)
$workspaceRoot = Split-Path -Parent $script:ScadRoot
$script:AppVersion = '1.0.4'
try {
    $v = (Get-Content -LiteralPath (Join-Path $workspaceRoot 'VERSION') -Raw).Trim()
    if ($v) { $script:AppVersion = $v }
} catch { }
$script:AppBuild = 0
try {
    $b = (Get-Content -LiteralPath (Join-Path $workspaceRoot 'BUILD') -Raw).Trim()
    [void][int]::TryParse($b, [ref]$script:AppBuild)
} catch { }
$script:AppVersionLabel = if ($script:AppBuild -gt 0) {
    "$($script:AppVersion)-dev.$($script:AppBuild)"
} else {
    $script:AppVersion
}
New-Item -ItemType Directory -Force -Path $script:StateDir | Out-Null
$script:StatePath = Join-Path $script:StateDir 'tray.json'
$script:LogPath = Join-Path $script:StateDir 'tray.log'
$script:ProgressDir = Join-Path (Split-Path -Parent $script:ScadRoot) 'scad-variants\state\progress'
$script:RendererStateDir = Join-Path (Split-Path -Parent $script:ScadRoot) 'scad-variants\state'
$script:UiSettingsPath = Join-Path $script:RendererStateDir 'ui-settings.json'
$script:GalleryServerState = Join-Path $script:RendererStateDir 'gallery-server.json'
$script:ServerStatusItem = $null
$script:ServerCpuLast = $null
$script:ServerCpuAt = $null

$script:AutoOpen = $false
$script:AutoOpenResults = $true
$script:Seen = [System.Collections.Generic.HashSet[string]]::new()
$script:Recent = @()
$script:LastProcessed = $null
$script:Pending = @{}
$script:RenderProcs = @{}
$script:RestartRequested = $false
$script:ProgressUi = @()
$script:MenuFilter = $null
$script:MenuTimer = $null
$script:MenuButtonWasDown = $false

function Write-TrayLog([string]$Message) {
    try {
        Add-Content -LiteralPath $script:LogPath -Encoding UTF8 `
            -Value ("{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message)
    } catch { }
}

function Normalize-Path([string]$Path) {
    return [IO.Path]::GetFullPath($Path).ToLowerInvariant()
}

function Get-OpenScadPath {
    # Prefer the portable Manifold-capable snapshot in the workspace.
    $tools = Join-Path (Split-Path -Parent $script:ScadRoot) 'tools'
    if (Test-Path -LiteralPath $tools) {
        $snapshots = @(
            Get-ChildItem -LiteralPath $tools -Directory -Filter 'openscad-*' `
                -ErrorAction SilentlyContinue | Sort-Object Name -Descending
        )
        foreach ($snapshot in $snapshots) {
            $candidate = Join-Path $snapshot.FullName 'openscad.exe'
            if (Test-Path -LiteralPath $candidate) { return $candidate }
        }
    }
    # The scoop shim is a console wrapper and opens a terminal. The
    # "current" junction also breaks older OpenSCAD builds (boost read_symlink),
    # so prefer a real versioned GUI executable.
    $appsRoot = Join-Path $env:USERPROFILE 'scoop\apps\openscad'
    if (Test-Path -LiteralPath $appsRoot) {
        $versions = @(
            Get-ChildItem -LiteralPath $appsRoot -Directory -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -ne 'current' } |
                Sort-Object Name -Descending
        )
        foreach ($version in $versions) {
            $candidate = Join-Path $version.FullName 'openscad.exe'
            if (Test-Path -LiteralPath $candidate) { return $candidate }
        }
    }
    $current = Join-Path $appsRoot 'current\openscad.exe'
    if (Test-Path -LiteralPath $current) { return $current }
    $cmd = Get-Command 'openscad.exe' -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $fallback = 'C:\Users\ak\scoop\shims\openscad.exe'
    if (Test-Path -LiteralPath $fallback) { return $fallback }
    return $null
}

function Get-OpenScadIconPath {
    # The scoop shim has a generic console icon; use the real OpenSCAD exe so
    # the tray icon is the recognizable yellow/green OpenSCAD logo.
    $actual = 'C:\Users\ak\scoop\apps\openscad\2021.01\openscad.exe'
    if (Test-Path -LiteralPath $actual) { return $actual }
    return (Get-OpenScadPath)
}

function Get-PythonwPath {
    $candidate = Join-Path $env:USERPROFILE '.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\pythonw.exe'
    if (Test-Path -LiteralPath $candidate) { return $candidate }
    $cmd = Get-Command 'pythonw.exe' -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Open-RenderPreview([string]$Index) {
    $pythonw = Get-PythonwPath
    $helper = Join-Path (Split-Path -Parent $script:ScadRoot) 'scad-variants\open_render.py'
    if ($pythonw -and (Test-Path -LiteralPath $helper)) {
        Start-Process -FilePath $pythonw -ArgumentList @($helper, $Index) -WindowStyle Hidden | Out-Null
        return
    }
    Start-Process -FilePath $Index | Out-Null
}

function Open-RenderFolder([string]$Index) {
    $folder = Split-Path -Parent $Index
    if ($folder -and (Test-Path -LiteralPath $folder)) {
        Start-Process -FilePath 'explorer.exe' -ArgumentList ('"' + $folder + '"') | Out-Null
    }
}

function Get-FolderMenuIcon {
    if ($script:FolderMenuIcon) { return $script:FolderMenuIcon }
    try {
        if (-not ('ScadFolderMenuIcon' -as [type])) {
            Add-Type -TypeDefinition @'
using System;
using System.Drawing;
using System.Runtime.InteropServices;

public static class ScadFolderMenuIcon
{
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct SHFILEINFO
    {
        public IntPtr hIcon;
        public int iIcon;
        public uint dwAttributes;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)]
        public string szDisplayName;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 80)]
        public string szTypeName;
    }

    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    public static extern IntPtr SHGetFileInfo(
        string pszPath, uint dwFileAttributes, ref SHFILEINFO psfi,
        uint cbFileInfo, uint uFlags);

    [DllImport("user32.dll")]
    public static extern bool DestroyIcon(IntPtr hIcon);

    public static Bitmap Load(string path)
    {
        SHFILEINFO info = new SHFILEINFO();
        IntPtr result = SHGetFileInfo(
            path, 0, ref info, (uint)Marshal.SizeOf(info), 0x00000101);
        if (result == IntPtr.Zero || info.hIcon == IntPtr.Zero) return null;
        try
        {
            using (Icon icon = Icon.FromHandle(info.hIcon))
            {
                return icon.ToBitmap();
            }
        }
        finally
        {
            DestroyIcon(info.hIcon);
        }
    }
}
'@ -ReferencedAssemblies System.Drawing
        }
        $script:FolderMenuIcon = [ScadFolderMenuIcon]::Load($env:SystemRoot)
    } catch {
        $script:FolderMenuIcon = $null
    }
    if (-not $script:FolderMenuIcon) {
        $script:FolderMenuIcon = [System.Drawing.SystemIcons]::Application.ToBitmap()
    }
    return $script:FolderMenuIcon
}

function Get-ScadFiles {
    if (-not (Test-Path -LiteralPath $script:Downloads)) { return @() }
    return @(
        Get-ChildItem -LiteralPath $script:Downloads -File -Filter '*.scad' `
            -ErrorAction SilentlyContinue | Sort-Object LastWriteTime
    )
}

function Get-RecentRenders {
    if (-not (Test-Path -LiteralPath $script:Downloads)) { return @() }
    $items = @()
    $manifests = @(
        Get-ChildItem -LiteralPath $script:Downloads -File -Filter 'manifest.json' `
            -Recurse -ErrorAction SilentlyContinue
    )
    foreach ($manifest in $manifests) {
        $folder = $manifest.Directory
        if (-not $folder) { continue }
        $index = Join-Path $folder.FullName 'index.html'
        if (-not (Test-Path -LiteralPath $index)) { continue }
        try {
            $data = Get-Content -LiteralPath $manifest.FullName -Raw | ConvertFrom-Json
        } catch {
            continue
        }
        if ($null -eq $data -or -not $data.source) { continue }

        $rawTime = [string]$data.updated_at
        $when = [datetime]::MinValue
        if (-not [datetime]::TryParse(
                $rawTime,
                [Globalization.CultureInfo]::InvariantCulture,
                [Globalization.DateTimeStyles]::RoundtripKind,
                [ref]$when)) {
            $when = $manifest.LastWriteTime
        }

        $base = $folder.Name
        if ($base -like '*_renders') {
            $name = $base.Substring(0, $base.Length - 8)
        } else {
            $name = [IO.Path]::GetFileNameWithoutExtension([string]$data.source.rel)
        }
        if (-not $name) { $name = $base }

        $items += [pscustomobject]@{
            Name = $name
            When = $when
            Date = $when.ToString('dd.MM.yyyy')
            Time = $when.ToString('HH:mm')
            Folder = $folder.FullName
            Index = $index
        }
    }
    return @($items | Sort-Object When -Descending | Select-Object -First 8)
}

function Get-ActiveRenderTasks {
    $dir = $script:ProgressDir
    if (-not (Test-Path -LiteralPath $dir)) { return @() }
    $tasks = @()
    foreach ($file in Get-ChildItem -LiteralPath $dir -Filter '*.json' -File -ErrorAction SilentlyContinue) {
        try {
            $data = Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json
        } catch {
            continue
        }
        if ($null -eq $data -or $data.status -ne 'running') { continue }
        $taskPid = 0
        [void][int]::TryParse([string]$data.pid, [ref]$taskPid)
        if ($taskPid -le 0) { continue }
        $proc = Get-Process -Id $taskPid -ErrorAction SilentlyContinue
        if (-not $proc) {
            Remove-Item -LiteralPath $file.FullName -Force -ErrorAction SilentlyContinue
            Write-TrayLog "removed stale progress: $($file.Name)"
            continue
        }
        $tasks += [pscustomobject]@{ File = $file; Data = $data }
    }
    return @($tasks | Sort-Object { $_.Data.started })
}

function Update-TrayTooltip {
    if (-not $script:NotifyIcon) { return }
    $tasks = @(Get-ActiveRenderTasks)
    if ($tasks.Count -eq 0) {
        $text = "SCAD Render $script:AppVersionLabel"
    } else {
        $first = $tasks[0].Data
        $text = "SCAD Render $script:AppVersionLabel — $($tasks.Count) задач: $($first.done)/$($first.total)"
    }
    if ($text.Length -gt 63) {
        $text = $text.Substring(0, 63)
    }
    try { $script:NotifyIcon.Text = $text } catch { }
}

function Get-CurrentPercent($Data) {
    $estimate = 0.0
    [void][double]::TryParse([string]$Data.current_estimate_s, [ref]$estimate)
    if ($estimate -le 0 -or -not $Data.current_started) { return $null }
    try {
        $start = [datetimeoffset]::Parse([string]$Data.current_started)
        $elapsed = ([datetimeoffset]::Now - $start).TotalSeconds
        if ($elapsed -lt 0) { $elapsed = 0 }
        return [Math]::Min(99, [int][Math]::Floor(100.0 * $elapsed / $estimate))
    } catch {
        return $null
    }
}

function Update-ServerStatus {
    if (-not $script:ServerStatusItem) { return }
    $text = 'Сервер: остановлен'
    $tip = 'Локальный сервер галереи не запущен'
    if (Test-Path -LiteralPath $script:GalleryServerState) {
        try {
            $state = Get-Content -LiteralPath $script:GalleryServerState -Raw | ConvertFrom-Json
            $serverPid = [int]$state.pid
            $port = [int]$state.port
            $proc = Get-Process -Id $serverPid -ErrorAction Stop
            $mem = [math]::Round($proc.WorkingSet64 / 1MB, 0)
            $now = Get-Date
            $cpuPct = 0.0
            if ($null -ne $script:ServerCpuLast -and $script:ServerCpuAt) {
                $elapsed = ($now - $script:ServerCpuAt).TotalSeconds
                if ($elapsed -gt 0.2) {
                    $cpuPct = (($proc.CPU - $script:ServerCpuLast) / $elapsed) * 100.0
                    if ($cpuPct -lt 0) { $cpuPct = 0 }
                    if ($cpuPct -gt 100) { $cpuPct = 100 }
                }
            }
            $script:ServerCpuLast = [double]$proc.CPU
            $script:ServerCpuAt = $now
            $text = "Сервер: работает :$port · $mem МБ · $([math]::Round($cpuPct, 1))% CPU"
            $tip = "PID $serverPid · 127.0.0.1:$port"
        } catch {
            $script:ServerCpuLast = $null
            $script:ServerCpuAt = $null
            $tip = 'Состояние сервера устарело'
        }
    } else {
        $script:ServerCpuLast = $null
        $script:ServerCpuAt = $null
    }
    $script:ServerStatusItem.Text = $text
    $script:ServerStatusItem.ToolTipText = $tip
}

function Update-ProgressMenu {
    Update-ServerStatus
    if (-not $script:Menu -or -not $script:Menu.Visible) { return }
    if ($script:ProgressUi.Count -eq 0) { return }

    $active = @(Get-ActiveRenderTasks)
    $byId = @{}
    foreach ($task in $active) {
        $byId[[string]$task.Data.id] = $task.Data
    }
    foreach ($ui in $script:ProgressUi) {
        if ($byId.ContainsKey($ui.Id)) {
            $data = $byId[$ui.Id]
            $done = [int]$data.done
            $total = [int]$data.total
            $percent = if ($total -gt 0) {
                [Math]::Min(100, [int][Math]::Round(100.0 * $done / $total))
            } else { 0 }
            $ui.Label.Text = "$($ui.Name) — $done из $total ($percent%)"
            $ui.Bar.Maximum = [Math]::Max(1, $total)
            $ui.Bar.Value = [Math]::Min($done, $ui.Bar.Maximum)

            $current = [string]$data.current
            $currentPercent = if ($current) { Get-CurrentPercent $data } else { $null }
            if ($ui.CurrentItem) {
                if ($current.Length -gt 60) {
                    $current = $current.Substring(0, 57) + '...'
                }
                if ($current) {
                    $text = '  текущий: ' + $current
                    if ($null -ne $currentPercent) { $text += " (~$currentPercent%)" }
                    $ui.CurrentItem.Text = $text
                    $ui.CurrentItem.Visible = $true
                } else {
                    $ui.CurrentItem.Text = ''
                    $ui.CurrentItem.Visible = $false
                }
            }
            if ($ui.CurrentBar) {
                if ($current) {
                    if ($null -eq $currentPercent) {
                        $ui.CurrentBar.Style = [System.Windows.Forms.ProgressBarStyle]::Marquee
                        $ui.CurrentBar.MarqueeAnimationSpeed = 30
                    } else {
                        $ui.CurrentBar.Style = [System.Windows.Forms.ProgressBarStyle]::Continuous
                        $ui.CurrentBar.Value = [Math]::Min(100, [Math]::Max(0, $currentPercent))
                    }
                    $ui.CurrentBar.Visible = $true
                } else {
                    $ui.CurrentBar.Visible = $false
                }
            }
        } else {
            $ui.Label.Text = "$($ui.Name) — завершено"
            $ui.Bar.Value = $ui.Bar.Maximum
            if ($ui.CurrentItem) {
                $ui.CurrentItem.Text = ''
                $ui.CurrentItem.Visible = $false
            }
            if ($ui.CurrentBar) { $ui.CurrentBar.Visible = $false }
        }
    }
}

function Save-RendererSettings {
    try {
        New-Item -ItemType Directory -Force -Path $script:RendererStateDir | Out-Null
        $payload = [ordered]@{ auto_open_results = [bool]$script:AutoOpenResults }
        $json = $payload | ConvertTo-Json
        $tmp = $script:UiSettingsPath + '.tmp'
        Set-Content -LiteralPath $tmp -Value $json -Encoding UTF8
        Move-Item -LiteralPath $tmp -Destination $script:UiSettingsPath -Force
        Write-TrayLog "auto_open_results=$($script:AutoOpenResults)"
    } catch {
        Write-TrayLog "settings save failed: $($_.Exception.Message)"
    }
}

function Load-RendererSettings {
    if (-not (Test-Path -LiteralPath $script:UiSettingsPath)) { return }
    try {
        $saved = Get-Content -LiteralPath $script:UiSettingsPath -Raw | ConvertFrom-Json
        if ($saved.PSObject.Properties.Name -contains 'auto_open_results') {
            $script:AutoOpenResults = [bool]$saved.auto_open_results
        }
    } catch {
        Write-TrayLog "settings read failed: $($_.Exception.Message)"
    }
}

function Save-TrayState {
    $payload = [ordered]@{
        auto_open      = [bool]$script:AutoOpen
        auto_open_results = [bool]$script:AutoOpenResults
        seen           = @($script:Seen)
        recent         = @($script:Recent)
        last_processed = $script:LastProcessed
    }
    $json = $payload | ConvertTo-Json -Depth 5
    $tmp = $script:StatePath + '.tmp'
    Set-Content -LiteralPath $tmp -Value $json -Encoding UTF8
    Move-Item -LiteralPath $tmp -Destination $script:StatePath -Force
}

function Load-TrayState {
    if (Test-Path -LiteralPath $script:StatePath) {
        try {
            $saved = Get-Content -LiteralPath $script:StatePath -Raw | ConvertFrom-Json
            $script:AutoOpen = [bool]$saved.auto_open
            if ($saved.PSObject.Properties.Name -contains 'auto_open_results') {
                $script:AutoOpenResults = [bool]$saved.auto_open_results
            }
            if ($saved.seen) {
                foreach ($item in @($saved.seen)) {
                    if ($item) { [void]$script:Seen.Add([string]$item) }
                }
            }
            if ($saved.recent) {
                $script:Recent = @($saved.recent | ForEach-Object { [string]$_ })
            }
            if ($saved.last_processed) {
                $script:LastProcessed = [string]$saved.last_processed
            }
        } catch {
            Write-TrayLog "state read failed: $($_.Exception.Message)"
        }
    }

    Load-RendererSettings

    $script:Seen.Clear()
    $script:Pending.Clear()
    $script:Recent = @()
}

function Add-Recent([string]$Path) {
    $key = Normalize-Path $Path
    $others = @(
        $script:Recent | Where-Object {
            $_ -and ((Normalize-Path $_) -ne $key)
        }
    )
    $script:Recent = @($Path) + $others
    if ($script:Recent.Count -gt 10) {
        $script:Recent = $script:Recent[0..9]
    }
}

function Start-OpenScad([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $exe = Get-OpenScadPath
    if (-not $exe) {
        Write-TrayLog 'OpenSCAD not found'
        return
    }
    try {
        Start-Process -FilePath $exe -ArgumentList ('"' + $Path + '"') | Out-Null
        $script:LastProcessed = $Path
        Save-TrayState
        Write-TrayLog "open in OpenSCAD: $Path"
    } catch {
        Write-TrayLog "open failed: $($_.Exception.Message)"
    }
}

function Start-Render([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $key = Normalize-Path $Path
    if ($script:RenderProcs.ContainsKey($key)) {
        $existing = $script:RenderProcs[$key]
        if ($existing -and -not $existing.HasExited) {
            Write-TrayLog "already rendering: $Path"
            return
        }
    }

    $pythonw = Get-PythonwPath
    if (-not $pythonw) {
        Write-TrayLog 'pythonw.exe not found'
        return
    }
    $dropScript = Join-Path $PSScriptRoot 'scad_drop.py'
    try {
        $argLine = '-u "' + $dropScript + '" --render-file "' + $Path + '"'
        $proc = Start-Process -FilePath $pythonw -ArgumentList $argLine `
            -WindowStyle Hidden -PassThru
        $script:RenderProcs[$key] = $proc
        $script:LastProcessed = $Path
        Save-TrayState
        Write-TrayLog "render: $Path"
    } catch {
        Write-TrayLog "render failed: $($_.Exception.Message)"
    }
}

function Exit-Tray {
    try { Save-TrayState } catch { }
    if ($script:NotifyIcon) {
        $script:NotifyIcon.Visible = $false
        $script:NotifyIcon.Dispose()
    }
    if ($script:MenuFilter) {
        [System.Windows.Forms.Application]::RemoveMessageFilter($script:MenuFilter)
        $script:MenuFilter = $null
    }
    if ($script:MenuTimer) {
        $script:MenuTimer.Stop()
        $script:MenuTimer.Dispose()
        $script:MenuTimer = $null
    }
    if ($script:Context) {
        $script:Context.ExitThread()
    } else {
        [System.Windows.Forms.Application]::Exit()
    }
}

function Restart-Tray {
    Write-TrayLog 'restart requested'
    $script:RestartRequested = $true
    Exit-Tray
}

function Get-RenderDir([string]$Path) {
    $folder = [IO.Path]::GetDirectoryName($Path)
    $name = [IO.Path]::GetFileNameWithoutExtension($Path)
    return (Join-Path $folder ($name + '_renders'))
}

function Open-RenderDir([string]$Path) {
    $renderDir = Get-RenderDir $Path
    if (-not (Test-Path -LiteralPath $renderDir)) {
        Write-TrayLog "render folder missing: $renderDir"
        return
    }
    Start-Process -FilePath 'explorer.exe' -ArgumentList ('"' + $renderDir + '"') | Out-Null
    Write-TrayLog "open render folder: $renderDir"
}

function Open-RenderHtml([string]$Path) {
    $renderDir = Get-RenderDir $Path
    $index = Join-Path $renderDir 'index.html'
    if (-not (Test-Path -LiteralPath $index)) {
        Write-TrayLog "gallery missing: $index"
        return
    }
    $pythonw = Get-PythonwPath
    $helper = Join-Path (Split-Path -Parent $script:ScadRoot) 'scad-variants\open_gallery.py'
    if (-not $pythonw -or -not (Test-Path -LiteralPath $helper)) {
        Write-TrayLog "gallery helper missing"
        return
    }
    $argLine = '"' + $helper + '" "' + $index + '"'
    Start-Process -FilePath $pythonw -ArgumentList $argLine -WindowStyle Hidden | Out-Null
    Write-TrayLog "open gallery isolated: $index"
}

function Add-FileActions($Items, [string]$Path) {
    $renderDir = Get-RenderDir $Path
    $hasResults = (Test-Path -LiteralPath $renderDir) -and (
        Test-Path -LiteralPath (Join-Path $renderDir 'index.html')
    )

    $open = New-Object System.Windows.Forms.ToolStripMenuItem
    $open.Text = 'Открыть в OpenSCAD'
    $open.Tag = $Path
    $open.ToolTipText = $Path
    $open.add_Click({ Start-OpenScad $this.Tag })
    [void]$Items.Add($open)

    $render = New-Object System.Windows.Forms.ToolStripMenuItem
    $render.Text = 'Запустить рендеринг'
    $render.Tag = $Path
    $render.ToolTipText = $Path
    $render.add_Click({ Start-Render $this.Tag })
    [void]$Items.Add($render)

    $results = New-Object System.Windows.Forms.ToolStripMenuItem
    $results.Text = 'Открыть результаты рендера'
    $results.Tag = $Path
    $results.Enabled = [bool]$hasResults
    $results.ToolTipText = if ($hasResults) {
        $renderDir
    } else {
        'Рендер ещё не завершён — готовой папки с результатами нет'
    }
    if ($hasResults) {
        $results.add_Click({ Open-RenderHtml $this.Tag })
    }
    [void]$Items.Add($results)

    $folder = New-Object System.Windows.Forms.ToolStripMenuItem
    $folder.Text = 'Открыть папку результатов'
    $folder.Tag = $Path
    $folder.Enabled = [bool]$hasResults
    $folder.ToolTipText = if ($hasResults) {
        $renderDir
    } else {
        'Рендер ещё не завершён — готовой папки нет'
    }
    if ($hasResults) {
        $folder.add_Click({ Open-RenderDir $this.Tag })
    }
    [void]$Items.Add($folder)
}

function Build-TrayMenu {
    try {
        $menu = $script:Menu
        $menu.ShowItemToolTips = $true
        $menu.Items.Clear()
        $script:ProgressUi = @()

        $activeTasks = @(Get-ActiveRenderTasks)
        $activeHeader = New-Object System.Windows.Forms.ToolStripMenuItem
        $activeHeader.Text = 'Активные задачи'
        $activeHeader.Enabled = $false
        [void]$menu.Items.Add($activeHeader)

        if ($activeTasks.Count -eq 0) {
            $noTasks = New-Object System.Windows.Forms.ToolStripMenuItem
            $noTasks.Text = 'Нет активных задач'
            $noTasks.Enabled = $false
            [void]$menu.Items.Add($noTasks)
        } else {
            foreach ($task in $activeTasks) {
                $data = $task.Data
                $done = [int]$data.done
                $total = [int]$data.total
                $percent = if ($total -gt 0) {
                    [Math]::Min(100, [int][Math]::Round(100.0 * $done / $total))
                } else { 0 }
                $item = New-Object System.Windows.Forms.ToolStripMenuItem
                $item.Text = "$($data.name) — $done из $total ($percent%)"
                $item.ToolTipText = [string]$data.source
                $item.Enabled = $false
                [void]$menu.Items.Add($item)

                $bar = New-Object System.Windows.Forms.ToolStripProgressBar
                $bar.Minimum = 0
                $bar.Maximum = [Math]::Max(1, $total)
                $bar.Value = [Math]::Min($done, $bar.Maximum)
                $bar.Width = 230
                $bar.Style = [System.Windows.Forms.ProgressBarStyle]::Continuous
                [void]$menu.Items.Add($bar)

                $currentItem = $null
                $currentBar = $null
                $current = [string]$data.current
                if ($current) {
                    if ($current.Length -gt 60) {
                        $current = $current.Substring(0, 57) + '...'
                    }
                    $currentPercent = Get-CurrentPercent $data
                    $currentText = '  текущий: ' + $current
                    if ($null -ne $currentPercent) {
                        $currentText += " (~$currentPercent%)"
                    }
                    $currentItem = New-Object System.Windows.Forms.ToolStripMenuItem
                    $currentItem.Text = $currentText
                    $currentItem.Enabled = $false
                    [void]$menu.Items.Add($currentItem)

                    $currentBar = New-Object System.Windows.Forms.ToolStripProgressBar
                    $currentBar.Minimum = 0
                    $currentBar.Maximum = 100
                    $currentBar.Width = 230
                    if ($null -eq $currentPercent) {
                        $currentBar.Style = [System.Windows.Forms.ProgressBarStyle]::Marquee
                        $currentBar.MarqueeAnimationSpeed = 30
                    } else {
                        $currentBar.Style = [System.Windows.Forms.ProgressBarStyle]::Continuous
                        $currentBar.Value = [Math]::Min(100, [Math]::Max(0, $currentPercent))
                    }
                    [void]$menu.Items.Add($currentBar)
                } else {
                    $currentItem = New-Object System.Windows.Forms.ToolStripMenuItem
                    $currentItem.Visible = $false
                    $currentItem.Enabled = $false
                    [void]$menu.Items.Add($currentItem)

                    $currentBar = New-Object System.Windows.Forms.ToolStripProgressBar
                    $currentBar.Minimum = 0
                    $currentBar.Maximum = 100
                    $currentBar.Width = 230
                    $currentBar.Visible = $false
                    [void]$menu.Items.Add($currentBar)
                }
                $script:ProgressUi += [pscustomobject]@{
                    Id = [string]$data.id
                    Name = [string]$data.name
                    Label = $item
                    Bar = $bar
                    CurrentItem = $currentItem
                    CurrentBar = $currentBar
                }
            }
        }

        $versionItem = New-Object System.Windows.Forms.ToolStripMenuItem
        $versionItem.Text = "Версия: $script:AppVersionLabel"
        $versionItem.Enabled = $false
        [void]$menu.Items.Add($versionItem)

        $serverStatus = New-Object System.Windows.Forms.ToolStripMenuItem
        $serverStatus.Enabled = $false
        $serverStatus.Text = 'Сервер: остановлен'
        $script:ServerStatusItem = $serverStatus
        [void]$menu.Items.Add($serverStatus)
        Update-ServerStatus

        [void]$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))

        $autoResults = New-Object System.Windows.Forms.ToolStripMenuItem
        $autoResults.Text = 'Автоматически открывать результаты в отдельном браузере'
        $autoResults.CheckOnClick = $true
        $autoResults.Checked = [bool]$script:AutoOpenResults
        $autoResults.add_Click({
            $script:AutoOpenResults = [bool]$this.Checked
            Save-TrayState
            Save-RendererSettings
            Write-TrayLog "auto_open_results=$($script:AutoOpenResults)"
        })
        [void]$menu.Items.Add($autoResults)
        [void]$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))

        $recentRenders = @(Get-RecentRenders)

        if ($recentRenders.Count -eq 0) {
            $empty = New-Object System.Windows.Forms.ToolStripMenuItem
            $empty.Text = 'Рендеров пока нет'
            $empty.Enabled = $false
            [void]$menu.Items.Add($empty)
        } else {
            $rendersHeader = New-Object System.Windows.Forms.ToolStripMenuItem
            $rendersHeader.Text = 'Недавние рендеры'
            $rendersHeader.Enabled = $false
            [void]$menu.Items.Add($rendersHeader)

            foreach ($render in $recentRenders) {
                $renderItem = New-Object System.Windows.Forms.ToolStripMenuItem
                $renderItem.Text = [string]$render.Name
                $renderItem.Tag = $render
                $defaultTip = $render.Name + ', ' + $render.Date + ' ' + $render.Time
                $renderItem.ToolTipText = $defaultTip
                $renderItem.Image = Get-FolderMenuIcon
                $renderItem.ImageScaling = [System.Windows.Forms.ToolStripItemImageScaling]::SizeToFit
                $renderItem.ImageAlign = [System.Drawing.ContentAlignment]::MiddleLeft
                $renderItem.ShowShortcutKeys = $true
                $renderItem.ShortcutKeyDisplayString = $render.Date + ' ' + $render.Time
                $renderItem.add_MouseMove({
                    param($sender, $eventArgs)
                    $tip = if ($eventArgs.X -lt 24) {
                        [string]$sender.Tag.Folder
                    } else {
                        [string]$sender.Tag.Name + ', ' + [string]$sender.Tag.Date + ' ' + [string]$sender.Tag.Time
                    }
                    if ($sender.ToolTipText -ne $tip) { $sender.ToolTipText = $tip }
                })
                $renderItem.add_MouseLeave({
                    param($sender, $eventArgs)
                    $sender.ToolTipText = [string]$sender.Tag.Name + ', ' + [string]$sender.Tag.Date + ' ' + [string]$sender.Tag.Time
                })
                $renderItem.add_MouseUp({
                    param($sender, $eventArgs)
                    if ($eventArgs.Button -ne [System.Windows.Forms.MouseButtons]::Left) { return }
                    if ($eventArgs.X -lt 24) {
                        Open-RenderFolder ([string]$sender.Tag.Index)
                    } else {
                        Open-RenderPreview ([string]$sender.Tag.Index)
                    }
                })
                [void]$menu.Items.Add($renderItem)
            }
        }

        [void]$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))

        $restart = New-Object System.Windows.Forms.ToolStripMenuItem
        $restart.Text = 'Перезагрузить программу'
        $restart.add_Click({ Restart-Tray })
        [void]$menu.Items.Add($restart)

        $exit = New-Object System.Windows.Forms.ToolStripMenuItem
        $exit.Text = 'Выход'
        $exit.add_Click({ Exit-Tray })
        [void]$menu.Items.Add($exit)
    } catch {
        Write-TrayLog "menu failed: $($_.Exception.Message)"
    }
}

$mutex = New-Object System.Threading.Mutex($false, ('Local\' + $InstanceName))
if (-not $mutex.WaitOne(0)) {
    exit 0
}

Load-TrayState

if ($SelfTest) {
    Write-Output ("OpenSCAD: " + (Get-OpenScadPath))
    $script:Menu = New-Object System.Windows.Forms.ContextMenuStrip
    Build-TrayMenu
    foreach ($item in $script:Menu.Items) {
        if ($item -is [System.Windows.Forms.ToolStripMenuItem]) {
            if ($item.DropDownItems.Count -gt 0) {
                $children = @(
                    $item.DropDownItems | ForEach-Object {
                        $suffix = if ($_.Enabled) { '' } else { ' [disabled]' }
                        $_.Text + $suffix
                    }
                ) -join ', '
                Write-Output ("{0} -> {1}" -f $item.Text, $children)
            } else {
                $suffix = if ($item.Enabled) { '' } else { ' [disabled]' }
                Write-Output ($item.Text + $suffix)
            }
        } else {
            Write-Output '---'
        }
    }
    $script:Menu.Dispose()
    exit 0
}

if ($SelfTestRestart) {
    $script:RestartRequested = $true
    Write-TrayLog 'selftest restart requested'
    exit 42
}

if ($SelfTestOpen) {
    Start-OpenScad $SelfTestOpen
    exit 0
}

if (-not $SelfTest -and -not $SelfTestRestart -and -not $SelfTestOpen) {
    Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;
namespace ScadTrayWin {
    public static class Native {
        [DllImport("kernel32.dll")]
        public static extern bool FreeConsole();
    }
}
'@
    [ScadTrayWin.Native]::FreeConsole() | Out-Null
}

$script:Context = New-Object System.Windows.Forms.ApplicationContext

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class ScadTrayWindow
{
    [DllImport("user32.dll")]
    private static extern int GetWindowLong(IntPtr hWnd, int nIndex);

    [DllImport("user32.dll")]
    private static extern int SetWindowLong(IntPtr hWnd, int nIndex, int dwNewLong);

    [DllImport("user32.dll")]
    private static extern bool SetWindowPos(
        IntPtr hWnd, IntPtr hWndInsertAfter, int x, int y, int cx, int cy, uint flags);

    public static void HideFromTaskbar(IntPtr hwnd)
    {
        const int GWL_EXSTYLE = -20;
        const int WS_EX_TOOLWINDOW = 0x00000080;
        const int WS_EX_APPWINDOW = 0x00040000;
        const uint SWP_NOSIZE = 0x0001;
        const uint SWP_NOMOVE = 0x0002;
        const uint SWP_NOZORDER = 0x0004;
        const uint SWP_NOACTIVATE = 0x0010;
        const uint SWP_FRAMECHANGED = 0x0020;

        int style = GetWindowLong(hwnd, GWL_EXSTYLE);
        style = (style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW;
        SetWindowLong(hwnd, GWL_EXSTYLE, style);
        SetWindowPos(
            hwnd, IntPtr.Zero, 0, 0, 0, 0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED);
    }
}
'@

$script:Menu = New-Object System.Windows.Forms.ContextMenuStrip
$script:Menu.add_Opening({
    $script:MenuButtonWasDown = [ScadTrayMenuFilter]::IsLeftButtonDown()
    Build-TrayMenu
})
$script:Menu.add_Opened({
    try {
        [ScadTrayWindow]::HideFromTaskbar($script:Menu.Handle)
    } catch { }
})

Add-Type -TypeDefinition @'
using System;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Windows.Forms;

public class ScadTrayMenuFilter : IMessageFilter
{
    public ToolStripDropDown Menu;

    [DllImport("user32.dll")]
    private static extern IntPtr WindowFromPoint(Point p);

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);

    [DllImport("user32.dll")]
    private static extern short GetAsyncKeyState(int vKey);

    public static bool IsLeftButtonDown()
    {
        return (GetAsyncKeyState(0x01) & 0x8000) != 0;
    }

    public static bool IsOtherProcess(Point point)
    {
        IntPtr hwnd = WindowFromPoint(point);
        uint pid;
        GetWindowThreadProcessId(hwnd, out pid);
        return pid != (uint)System.Diagnostics.Process.GetCurrentProcess().Id;
    }

    public bool PreFilterMessage(ref Message m)
    {
        if (Menu == null || !Menu.Visible) return false;
        if (m.Msg != 0x0201 && m.Msg != 0x0204 && m.Msg != 0x0207
            && m.Msg != 0x00A1 && m.Msg != 0x00A4) return false;

        IntPtr hwnd = WindowFromPoint(Cursor.Position);
        uint pid;
        GetWindowThreadProcessId(hwnd, out pid);
        if (pid != (uint)System.Diagnostics.Process.GetCurrentProcess().Id)
        {
            Menu.Close(ToolStripDropDownCloseReason.AppClicked);
        }
        return false;
    }
}
'@ -ReferencedAssemblies 'System.Windows.Forms', 'System.Drawing' | Out-Null

$script:MenuFilter = New-Object ScadTrayMenuFilter
$script:MenuFilter.Menu = $script:Menu
[void][System.Windows.Forms.Application]::AddMessageFilter($script:MenuFilter)

$script:MenuTimer = New-Object System.Windows.Forms.Timer
$script:MenuTimer.Interval = 50
$script:MenuTimer.add_Tick({
    if (-not $script:Menu -or -not $script:Menu.Visible) {
        $script:MenuButtonWasDown = $false
        return
    }
    $down = [ScadTrayMenuFilter]::IsLeftButtonDown()
    if ($down -and -not $script:MenuButtonWasDown) {
        if ([ScadTrayMenuFilter]::IsOtherProcess([System.Windows.Forms.Cursor]::Position)) {
            $script:Menu.Close([System.Windows.Forms.ToolStripDropDownCloseReason]::AppClicked)
        }
    }
    $script:MenuButtonWasDown = $down
})
$script:MenuTimer.Start()

$iconPath = Get-OpenScadIconPath
$icon = $null
if ($iconPath) {
    try { $icon = [System.Drawing.Icon]::ExtractAssociatedIcon($iconPath) } catch { }
}
if (-not $icon) { $icon = [System.Drawing.SystemIcons]::Application }

$script:NotifyIcon = New-Object System.Windows.Forms.NotifyIcon
$script:NotifyIcon.Icon = $icon
$script:NotifyIcon.Text = "SCAD Render $script:AppVersionLabel"
$script:NotifyIcon.ContextMenuStrip = $script:Menu
$script:NotifyIcon.Visible = $true
$script:NotifyIcon.add_MouseClick({
    if ($_.Button -eq [System.Windows.Forms.MouseButtons]::Left) {
        $script:Menu.Show([System.Windows.Forms.Cursor]::Position)
    }
})
Update-TrayTooltip

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 2000
$timer.add_Tick({
    Update-TrayTooltip
    Update-ProgressMenu
})
$timer.Start()

Write-TrayLog 'tray started'
Write-TrayLog "notify icon visible=$($script:NotifyIcon.Visible)"

try {
    [System.Windows.Forms.Application]::Run($script:Context)
} catch {
    Write-TrayLog "fatal: $($_.Exception.ToString())"
}
Write-TrayLog 'tray loop exited'

$timer.Stop()
$timer.Dispose()
if ($script:MenuTimer) {
    $script:MenuTimer.Stop()
    $script:MenuTimer.Dispose()
    $script:MenuTimer = $null
}
$script:NotifyIcon.Visible = $false
$script:NotifyIcon.Dispose()
$mutex.ReleaseMutex()

if ($script:RestartRequested) {
    exit 42
}
