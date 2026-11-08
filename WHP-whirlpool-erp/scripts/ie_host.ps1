param(
    [string]$Url = "https://erp.whirlpool-china.com:4446/OA_HTML/AppsLogin",
    [string]$Cmd = "E:\SKILLS\WHP-whirlpool-erp\logs\ie_cmd.txt",
    [string]$Status = "E:\SKILLS\WHP-whirlpool-erp\logs\ie_status.txt"
)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# 让宿主变成 DPI 感知，否则 Win10/11 会把窗口坐标虚拟化，截图和点击会错位
$sig = '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'
try { Add-Type -MemberDefinition $sig -Name Dpi -Namespace Win32 | Out-Null; [Win32.Dpi]::SetProcessDPIAware() | Out-Null } catch { }

$form = New-Object System.Windows.Forms.Form
$form.Text = "EBS-IE"
$form.StartPosition = "Manual"
$form.Left = 0
$form.Top = 0
$form.FormBorderStyle = "None"
$form.WindowState = "Maximized"

$wb = New-Object System.Windows.Forms.WebBrowser
$wb.Dock = "Fill"
$wb.ScriptErrorsSuppressed = $true
$wb.AllowNavigation = $true
$wb.IsWebBrowserContextMenuEnabled = $false
$form.Controls.Add($wb)
$form.Show()

$script:lastCmd = ""
try { $script:lastCmd = (Get-Content $Cmd -Raw -ErrorAction SilentlyContinue) } catch { }
$wb.Navigate($Url)

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 700
$timer.Add_Tick({
    try {
        $c = (Get-Content $Cmd -Raw -ErrorAction SilentlyContinue)
        if ($c) { $c = $c.Trim() }
        if ($c -and $c -ne $script:lastCmd) {
            $script:lastCmd = $c
            $wb.Navigate($c)
        }
    } catch { }
    try {
        $u = ""
        $t = ""
        try { $u = $wb.Url.AbsoluteUri } catch { }
        try { $t = $wb.DocumentTitle } catch { }
        [System.IO.File]::WriteAllText($Status, "$($wb.ReadyState)`t$u`t$t")
    } catch { }
})
$timer.Start()
[System.Windows.Forms.Application]::Run($form)