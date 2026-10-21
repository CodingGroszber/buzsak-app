#Requires -Version 7
<#
.SYNOPSIS
  Generate a local, secret-scanned project reference snapshot (DOC-11, SEC-04).
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    if (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
        throw 'Node.js/npm is required for Repomix. Install Node.js, then retry.'
    }
    & npx --yes repomix@1.18.1 --config repomix.config.json
    if ($LASTEXITCODE -ne 0) { throw "Repomix failed (exit $LASTEXITCODE)." }
}
finally { Pop-Location }