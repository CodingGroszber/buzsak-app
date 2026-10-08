#Requires -Version 7
<#
.SYNOPSIS
  Live run on a device or emulator with Flet's debug tooling (BLD-03).
.DESCRIPTION
  `flet debug android` packages the whole app and runs it on the device, so what you see is what
  an installed APK does, including real Android networking. Needs Windows Developer Mode.
.PARAMETER Serial
  Device id from `flet devices`. Required only when more than one device is attached.
#>
[CmdletBinding()]
param([string]$Serial)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')

Assert-DeveloperMode
$device = Resolve-DeviceSerial -Serial $Serial
Set-Location $script:RepoRoot
$env:FLET_CLI_NO_RICH_OUTPUT = '1'
uv run flet debug android --device-id $device --yes --no-rich-output
