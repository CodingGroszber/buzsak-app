#Requires -Version 7
<#
.SYNOPSIS
  One step to see the app on a device: build, install and launch (BLD-04, BLD-06).
.PARAMETER SkipBuild
  Reuse the newest APK in build/apk.
.PARAMETER Logs
  Follow the app's log afterwards (Ctrl+C to stop).
#>
[CmdletBinding()]
param([string]$Serial, [switch]$SkipBuild, [switch]$Logs)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')

# Fail fast on a missing device before spending minutes on a build.
$device = Resolve-DeviceSerial -Serial $Serial

if (-not $SkipBuild) { & (Join-Path $PSScriptRoot 'build-debug.ps1') }
& (Join-Path $PSScriptRoot 'install.ps1') -Serial $device
if ($Logs) { & (Join-Path $PSScriptRoot 'logs.ps1') -Serial $device }
