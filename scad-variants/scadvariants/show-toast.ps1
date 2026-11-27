param(
    [Parameter(Mandatory = $true)][string]$Title,
    [Parameter(Mandatory = $true)][string]$Body,
    [string]$Launch = "",
    [string]$Aumid = "ScadDrop.Render"
)

$ErrorActionPreference = "Stop"

$shown = $false
try {
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

    $template = '<toast><visual><binding template="ToastGeneric"><text id="1"></text><text id="2"></text></binding></visual></toast>'
    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $xml.LoadXml($template)

    $texts = $xml.GetElementsByTagName("text")
    $texts.Item(0).InnerText = $Title
    $texts.Item(1).InnerText = $Body

    if ($Launch) {
        $xml.DocumentElement.SetAttribute("activationType", "protocol")
        $xml.DocumentElement.SetAttribute("launch", $Launch)
    }

    $toast = New-Object Windows.UI.Notifications.ToastNotification $xml

    # A Start Menu shortcut registers the AUMID; the process must also declare
    # it, otherwise ToastNotificationManager reports "no package identity".
    Add-Type -Namespace ScadToast -Name Shell -MemberDefinition @'
[DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = true)]
public static extern int SetCurrentProcessExplicitAppUserModelID(string appID);
'@
    $hr = [ScadToast.Shell]::SetCurrentProcessExplicitAppUserModelID($Aumid)
    Write-Output "setaumid=$hr"
    $null = $hr

    $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($Aumid)
    $notifier.Show($toast)
    Write-Output "toast: primary"
    $shown = $true
} catch {
    Write-Output "toast: fallback ($($_.Exception.Message))"
    # No registered AUMID / WinRT unavailable: fall back to a tray balloon.
    try {
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        $icon = New-Object System.Windows.Forms.NotifyIcon
        $icon.Icon = [System.Drawing.SystemIcons]::Information
        $icon.Visible = $true
        $icon.ShowBalloonTip(8000, $Title, $Body, [System.Windows.Forms.ToolTipIcon]::Info)
        $end = (Get-Date).AddSeconds(6)
        while ((Get-Date) -lt $end) {
            [System.Windows.Forms.Application]::DoEvents()
            Start-Sleep -Milliseconds 100
        }
        $icon.Dispose()
        $shown = $true
    } catch {
        Write-Error "Notification failed: $($_.Exception.Message)"
    }
}

if ($shown) {
    exit 0
}
exit 1
