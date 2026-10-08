#Requires -Version 7
<#
.SYNOPSIS
  Installs the APK on a device or emulator and optionally launches it (BLD-06).
.PARAMETER Serial
  Device id from `adb devices`. Required only when more than one device is attached.
.PARAMETER Apk
  APK path; defaults to the newest file in build/apk.
.PARAMETER NoLaunch
  Install only.
#>
[CmdletBinding()]
param([string]$Serial, [string]$Apk, [switch]$NoLaunch)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')

$adb = Get-Adb
$device = Resolve-DeviceSerial -Serial $Serial
$apkPath = Find-Apk -Path $Apk

"Installing $(Split-Path $apkPath -Leaf) on $device ..."
& $adb -s $device install -r $apkPath
if ($LASTEXITCODE -ne 0) { throw "adb install failed (exit $LASTEXITCODE)." }

if (-not $NoLaunch) {
    # `monkey` starts the launcher activity without needing its class name.
    & $adb -s $device shell monkey -p $script:PackageId -c android.intent.category.LAUNCHER 1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Installed, but launching failed. Open the app from the launcher.' }
    "Launched $script:PackageId on $device."
}
