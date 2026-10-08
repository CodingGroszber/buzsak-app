#Requires -Version 7
<#
.SYNOPSIS
  Desktop dev run with hot reload (BLD-01).
.PARAMETER Web
  Run in the browser instead of a desktop window.
.PARAMETER FakeServer
  Start a local fake API and prefill its non-secret test credential in the app.
.PARAMETER LiveServer
  Read the provisioned operator token from the Pi over SSH for this desktop session only.
#>
[CmdletBinding()]
param(
    [switch]$Web,
    [switch]$FakeServer,
    [switch]$LiveServer
)

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

$flags = @('-d', '-r')
if ($Web) { $flags += '--web' }
$fakeServerProcess = $null
if ($FakeServer -and $LiveServer) {
  throw 'Choose either -FakeServer or -LiveServer, not both.'
}

if ($FakeServer) {
  $previewPort = 8765
  while (Get-NetTCPConnection -State Listen -LocalPort $previewPort -ErrorAction SilentlyContinue) {
    $previewPort++
    if ($previewPort -gt 65535) { throw 'No local preview port is available.' }
  }

  $pythonPath = (uv run python -c "import sys; print(sys.executable)").Trim()
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Could not locate the project Python interpreter for the fake API.'
  }

  $fakeServerPath = Join-Path $PSScriptRoot 'fake_server.py'
  $fakeServerArguments = "-u `"$fakeServerPath`" --host 127.0.0.1 --port $previewPort --scenario normal"
  $fakeServerProcess = Start-Process -FilePath $pythonPath `
    -ArgumentList $fakeServerArguments -PassThru -WindowStyle Hidden
  $env:BUZSAK_FAKE_SERVER_PREVIEW = '1'
  $env:BUZSAK_FAKE_SERVER_PORT = [string]$previewPort
  Write-Host "Fake API: http://127.0.0.1:$previewPort (token: fake-operator; no hardware access)"
}

if ($LiveServer) {
  $tokenValue = ssh rpi3 'cat /home/neulas/.buzsak-operator-token'
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace(($tokenValue -join "`n"))) {
    Remove-Variable tokenValue -ErrorAction SilentlyContinue
    throw 'Could not retrieve the provisioned operator token from rpi3.'
  }
  $env:BUZSAK_LIVE_SERVER_TOKEN = ($tokenValue -join "`n").Trim()
  Remove-Variable tokenValue
  $env:BUZSAK_LIVE_SERVER_SESSION = '1'
  Write-Host 'Live server: https://192.168.1.95 (operator credential loaded; token hidden). Commands can actuate hardware.'
}

try {
  uv run flet run @flags src/main.py
}
finally {
  if ($FakeServer) {
    Remove-Item Env:BUZSAK_FAKE_SERVER_PREVIEW -ErrorAction SilentlyContinue
    Remove-Item Env:BUZSAK_FAKE_SERVER_PORT -ErrorAction SilentlyContinue
    if ($fakeServerProcess -and -not $fakeServerProcess.HasExited) {
      Stop-Process -Id $fakeServerProcess.Id -Force -ErrorAction SilentlyContinue
    }
  }
  if ($LiveServer) {
    Remove-Item Env:BUZSAK_LIVE_SERVER_SESSION -ErrorAction SilentlyContinue
    Remove-Item Env:BUZSAK_LIVE_SERVER_TOKEN -ErrorAction SilentlyContinue
  }
}
