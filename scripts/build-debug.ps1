#Requires -Version 7
<#
.SYNOPSIS
  Builds an installable APK for local testing (BLD-04).
.DESCRIPTION
  Runs `flet build apk`. Without signing variables the APK is signed with the debug key, which is
  fine for installing on your own devices. First build downloads Flutter and Android components.
  Release signing is a separate step (BLD-05, backlog B-301).
#>
[CmdletBinding()]
param([switch]$VerboseBuild)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')

Assert-DeveloperMode
Set-Location $script:RepoRoot

$flags = @('--yes', '--no-rich-output')
if ($VerboseBuild) { $flags += '-v' }
$env:FLET_CLI_NO_RICH_OUTPUT = '1'
# Flutter prints a check mark after a good build; without UTF-8 Flet's logger crashes on it when
# output is piped (cp1252) and reports a failure even though the APK was built.
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

uv run flet build apk @flags
if ($LASTEXITCODE -ne 0) { throw "flet build failed (exit $LASTEXITCODE). See the log above." }

$apk = Find-Apk
"APK: $apk ($([math]::Round((Get-Item $apk).Length / 1MB, 1)) MB)"
