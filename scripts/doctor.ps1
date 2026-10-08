#Requires -Version 7
<#
.SYNOPSIS
  Checks the Windows 11 + Android Studio toolchain for building Buzsák App (BLD-09).
.DESCRIPTION
  Read-only. Prints OK / WARN / FAIL per check and exits 1 if any FAIL.
  WARN means the build can still proceed (e.g. Flet downloads a missing Flutter SDK itself).
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$script:failures = 0

function Write-Check {
    param([ValidateSet('OK', 'WARN', 'FAIL')][string]$Status, [string]$Name, [string]$Detail, [string]$Fix)
    $color = @{ OK = 'Green'; WARN = 'Yellow'; FAIL = 'Red' }[$Status]
    Write-Host ('[{0,-4}] ' -f $Status) -ForegroundColor $color -NoNewline
    Write-Host ('{0}: {1}' -f $Name, $Detail)
    if ($Fix -and $Status -ne 'OK') { Write-Host "       fix: $Fix" -ForegroundColor DarkGray }
    if ($Status -eq 'FAIL') { $script:failures++ }
}

function Get-FirstLine { param($Text) ($Text | Out-String).Trim().Split("`n")[0].Trim() }

# uv
$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($uv) { Write-Check OK 'uv' (Get-FirstLine (& uv --version)) }
else { Write-Check FAIL 'uv' 'not found on PATH' 'Install uv: https://docs.astral.sh/uv/' }

# Project environment (Python + pinned Flet)
if ($uv) {
    Push-Location (Split-Path $PSScriptRoot -Parent)
    try {
        $flet = & uv run --quiet flet --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Check OK 'flet' ((Get-FirstLine $flet) + ' (from uv.lock)')
        } else {
            Write-Check FAIL 'flet' 'project environment not usable' 'Run: uv sync'
        }
    } finally { Pop-Location }
}

# Flutter (Flet downloads the version it needs, so a mismatch is only informational)
$flutter = Get-Command flutter -ErrorAction SilentlyContinue
if ($flutter) { Write-Check OK 'flutter' $flutter.Source }
else { Write-Check WARN 'flutter' 'not on PATH' 'Flet will download the required SDK into ~/flutter on first build' }

# JDK 17 (Flet requirement)
$java = Get-Command java -ErrorAction SilentlyContinue
if ($java) {
    $ver = Get-FirstLine (& $java.Source -version 2>&1)
    if ($ver -match '"17\.') { Write-Check OK 'jdk' $ver }
    else { Write-Check WARN 'jdk' "$ver (JDK 17 expected)" 'Install JDK 17 or let Flet install one into ~/java' }
} else {
    Write-Check WARN 'jdk' 'java not on PATH' 'Flet will install JDK 17 into ~/java on first build'
}

# Developer Mode: Flutter needs symlink support on Windows to build Android apps (flet build fails without it)
$devMode = (Get-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock' -ErrorAction SilentlyContinue)?.AllowDevelopmentWithoutDevLicense -eq 1
if ($devMode) { Write-Check OK 'developer mode' 'enabled' }
else { Write-Check FAIL 'developer mode' 'off; Android builds will fail on symlinks' 'Settings > System > For developers > Developer Mode (or: start ms-settings:developers)' }

# Android SDK
$sdk = @($env:ANDROID_HOME, $env:ANDROID_SDK_ROOT, (Join-Path $env:LOCALAPPDATA 'Android\Sdk')) |
    Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if ($sdk) { Write-Check OK 'android sdk' $sdk }
else { Write-Check FAIL 'android sdk' 'not found' 'Install Android Studio and set ANDROID_HOME' }

# adb
$adb = (Get-Command adb -ErrorAction SilentlyContinue)?.Source
if (-not $adb -and $sdk) {
    $candidate = Join-Path $sdk 'platform-tools\adb.exe'
    if (Test-Path -LiteralPath $candidate) { $adb = $candidate }
}
if ($adb) {
    Write-Check OK 'adb' $adb
    $lines = (& $adb devices) | Select-Object -Skip 1 | Where-Object { $_.Trim() }
    if ($lines) {
        foreach ($l in $lines) { Write-Check OK 'device' ($l -replace '\s+', ' ') }
    } else {
        Write-Check WARN 'device' 'no device or emulator attached' 'Start an AVD or enable USB debugging (see docs/build-and-deploy.md)'
    }
} else {
    Write-Check FAIL 'adb' 'not found' 'Add Android SDK platform-tools to PATH'
}

if ($script:failures) { Write-Host "`n$script:failures check(s) failed." -ForegroundColor Red; exit 1 }
Write-Host "`nEnvironment looks good." -ForegroundColor Green
