#Requires -Version 7
<#
.SYNOPSIS
  Clicks at window-relative pixel coordinates in a top-level window (dev aid for driving the desktop UI).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Title,
    [Parameter(Mandatory)][int]$X,
    [Parameter(Mandatory)][int]$Y,
    [string]$ProcessName = '*'
)

Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class WinClick {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
'@
[void][WinClick]::SetProcessDPIAware()

$proc = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowTitle -like "*$Title*" -and $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $proc) { throw "No window with title containing '$Title' (process '$ProcessName')" }

$rect = New-Object WinClick+RECT
[void][WinClick]::GetWindowRect($proc.MainWindowHandle, [ref]$rect)
[void][WinClick]::SetForegroundWindow($proc.MainWindowHandle)
Start-Sleep -Milliseconds 300
[void][WinClick]::SetCursorPos($rect.Left + $X, $rect.Top + $Y)
Start-Sleep -Milliseconds 100
[WinClick]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)  # left down
[WinClick]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)  # left up
"clicked ($X,$Y) in '$($proc.MainWindowTitle)'"
