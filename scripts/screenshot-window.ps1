#Requires -Version 7
<#
.SYNOPSIS
  Captures a screenshot of a top-level window by title substring (dev aid for checking the UI).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Title,
    [Parameter(Mandatory)][string]$OutFile,
    [string]$ProcessName = '*'
)

Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class WinCap {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
'@
[void][WinCap]::SetProcessDPIAware()

$proc = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowTitle -like "*$Title*" -and $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $proc) { throw "No window with title containing '$Title' (process '$ProcessName')" }

$rect = New-Object WinCap+RECT
[void][WinCap]::GetWindowRect($proc.MainWindowHandle, [ref]$rect)
$w = $rect.Right - $rect.Left; $h = $rect.Bottom - $rect.Top
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
# Flag 2 = PW_RENDERFULLCONTENT, needed for GPU-rendered (Flutter) windows.
[void][WinCap]::PrintWindow($proc.MainWindowHandle, $hdc, 2)
$g.ReleaseHdc($hdc); $g.Dispose()
$bmp.Save($OutFile, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
"saved $OutFile (${w}x${h})"
