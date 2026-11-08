param([string]$Url, [int]$W = 1500, [int]$H = 980, [int]$L = 40, [int]$T = 30)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$form = New-Object System.Windows.Forms.Form
$form.Text = "EBS-IE"
$form.Width = $W
$form.Height = $H
$form.StartPosition = "Manual"
$form.Left = $L
$form.Top = $T
$wb = New-Object System.Windows.Forms.WebBrowser
$wb.Dock = "Fill"
$wb.ScriptErrorsSuppressed = $true
$wb.AllowNavigation = $true
$form.Controls.Add($wb)
$form.Show()
$wb.Navigate($Url)
[System.Windows.Forms.Application]::Run($form)