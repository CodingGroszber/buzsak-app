#Requires -Version 7
<#
.SYNOPSIS
  Starts an Android emulator (AVD) and waits until it has booted (BLD-02).
.PARAMETER Avd
  AVD name; defaults to the first one listed by `emulator -list-avds`.
.PARAMETER List
  Only list the available AVDs.
#>
[CmdletBinding()]
param([string]$Avd, [switch]$List, [int]$BootTimeoutSeconds = 240)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')

$sdk = Get-AndroidSdk
if (-not $sdk) { throw 'Android SDK not found. Install Android Studio and set ANDROID_HOME.' }
$emulator = Join-Path $sdk 'emulator\emulator.exe'
if (-not (Test-Path -LiteralPath $emulator)) { throw "emulator.exe not found under $sdk. Install it via Android Studio's SDK Manager." }

$avds = @(& $emulator -list-avds | Where-Object { $_.Trim() })
if ($List) { $avds; return }
if (-not $avds) { throw 'No AVD found. Create one in Android Studio > Device Manager.' }
if (-not $Avd) { $Avd = $avds[0] }
if ($Avd -notin $avds) { throw "Unknown AVD '$Avd'. Available: $($avds -join ', ')" }

$adb = Get-Adb
$running = @(Get-AttachedDevices | Where-Object { $_ -like 'emulator-*' })
if ($running) {
    "An emulator is already running: $($running -join ', ')"
    return
}

"Starting $Avd ..."
Start-Process -FilePath $emulator -ArgumentList '-avd', $Avd, '-no-snapshot-save' -WindowStyle Hidden

$deadline = (Get-Date).AddSeconds($BootTimeoutSeconds)
& $adb wait-for-device
do {
    Start-Sleep -Seconds 3
    $booted = (& $adb shell getprop sys.boot_completed 2>$null) -join ''
    if ($booted.Trim() -eq '1') { break }
} while ((Get-Date) -lt $deadline)
if ($booted.Trim() -ne '1') { throw "Emulator did not finish booting within $BootTimeoutSeconds s." }
"Emulator ready: $((Get-AttachedDevices) -join ', ')"
