Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repo = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repo

$port = 8787
$uri = "http://localhost:$port/dash/control_tower.html"

Write-Host "Serving repo root on $uri"
Write-Host "Tip: si Windows te pregunta firewall, permite 'Private networks'."

Start-Process $uri
python -m http.server $port --directory .
