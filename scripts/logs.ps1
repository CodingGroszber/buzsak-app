#Requires -Version 7
<#
.SYNOPSIS
  Shows the app's Python output and crashes from a device (BLD-07).
.DESCRIPTION
  The Flet runtime sends print()/logging to logcat under the tag `flet.python`; native crashes
  appear under AndroidRuntime. Output is not filtered further, so nothing is hidden.
.PARAMETER Clear
  Clear the device log buffer first, so only this run is shown.
.PARAMETER Dump
  Print what is buffered and exit instead of following.
#>
[CmdletBinding()]
param([string]$Serial, [switch]$Clear, [switch]$Dump)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')

$adb = Get-Adb
$device = Resolve-DeviceSerial -Serial $Serial

if ($Clear) { & $adb -s $device logcat -c }
$logcatArgs = @('-s', $device, 'logcat')
if ($Dump) { $logcatArgs += '-d' }
# `*:S` silences everything else; the tags below are the app's Python output and Android crashes.
$logcatArgs += @('flet.python:V', 'AndroidRuntime:E', 'DEBUG:E', '*:S')
& $adb @logcatArgs
