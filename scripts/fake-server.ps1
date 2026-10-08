#Requires -Version 7
<#
.SYNOPSIS
  Run the simulated telemetry and valve-command API for safe UI testing (BLD-08, TST-06).
.PARAMETER Scenario
  normal, stale, offline, malformed, failure, uncertain or slow.
#>
[CmdletBinding()]
param(
    [ValidateSet('normal', 'stale', 'offline', 'malformed', 'failure', 'uncertain', 'slow')]
    [string]$Scenario = 'normal',
    [int]$Port = 8765
)

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
uv run python scripts/fake_server.py --host 0.0.0.0 --port $Port --scenario $Scenario
