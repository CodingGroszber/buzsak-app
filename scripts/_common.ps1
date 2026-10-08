#Requires -Version 7
# Shared helpers for the build/deploy scripts (BLD-02..BLD-07). Dot-source this file.

Set-StrictMode -Version Latest

$script:RepoRoot = Split-Path $PSScriptRoot -Parent
# Flet derives this from [tool.flet].org and the project name (verified in build/flutter/android).
$script:PackageId = 'hu.buzsak.buzsak_app'

function Get-AndroidSdk {
    $candidates = @($env:ANDROID_HOME, $env:ANDROID_SDK_ROOT, (Join-Path $env:LOCALAPPDATA 'Android\Sdk'))
    $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
}

function Get-Adb {
    $cmd = Get-Command adb -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $sdk = Get-AndroidSdk
    if ($sdk) {
        $candidate = Join-Path $sdk 'platform-tools\adb.exe'
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    throw 'adb not found. Install Android Studio or add platform-tools to PATH (see docs/build-and-deploy.md).'
}

function Get-AttachedDevices {
    <# Serials of devices in the "device" state (skips offline/unauthorized, which cannot be used). #>
    $adb = Get-Adb
    $lines = & $adb devices | Select-Object -Skip 1 | Where-Object { $_.Trim() }
    foreach ($line in $lines) {
        $parts = $line -split '\s+'
        if ($parts.Count -ge 2 -and $parts[1] -eq 'device') { $parts[0] }
        elseif ($parts.Count -ge 2) { Write-Warning "Ignoring $($parts[0]): state is '$($parts[1])' (accept the USB debugging prompt?)" }
    }
}

function Resolve-DeviceSerial {
    param([string]$Serial)
    if ($Serial) { return $Serial }
    $devices = @(Get-AttachedDevices)
    switch ($devices.Count) {
        0 { throw 'No Android device or emulator attached. Plug in a phone with USB debugging, or run scripts/emulator.ps1.' }
        1 { return $devices[0] }
        default { throw "$($devices.Count) devices attached ($($devices -join ', ')). Pass -Serial <id>." }
    }
}

function Find-Apk {
    param([string]$Path)
    if ($Path) {
        if (-not (Test-Path -LiteralPath $Path)) { throw "APK not found: $Path" }
        return (Resolve-Path -LiteralPath $Path).Path
    }
    $apkDir = Join-Path $script:RepoRoot 'build\apk'
    $apk = Get-ChildItem -LiteralPath $apkDir -Filter '*.apk' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $apk) {
        # Flet copies the APK to build/apk at the very end; Flutter's own output exists earlier.
        $flutterDir = Join-Path $script:RepoRoot 'build\flutter\build\app\outputs\flutter-apk'
        $apk = Get-ChildItem -LiteralPath $flutterDir -Filter '*.apk' -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
    }
    if (-not $apk) { throw "No APK in $apkDir. Run scripts/build-debug.ps1 first." }
    $apk.FullName
}

function Test-DeveloperMode {
    # Flutter needs symlink support on Windows; Developer Mode provides it without elevation.
    $key = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock'
    (Get-ItemProperty -Path $key -ErrorAction SilentlyContinue)?.AllowDevelopmentWithoutDevLicense -eq 1
}

function Assert-DeveloperMode {
    if (-not (Test-DeveloperMode)) {
        throw @'
Windows Developer Mode is off, and Flutter needs it to build Android apps (symlink support).
Turn it on in Settings > System > For developers > Developer Mode, then run this again.
(Or run: start ms-settings:developers)
'@
    }
}
