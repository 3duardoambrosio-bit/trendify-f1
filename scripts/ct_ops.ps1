# scripts/ct_ops.ps1
<#
SYNAPSE  Control Tower Ops (SIM)
marker: CT_OPS_PS1_2026-01-20_V8_CANON_SNAPSHOT

Uso:
  powershell -ExecutionPolicy Bypass -File .\scripts\ct_ops.ps1 -Sim -Serve -Open
#>

param(
  [switch]$Sim,
  [switch]$Serve,
  [switch]$Open,
  [switch]$NoSnapshot,
  [int]$Port = 8787,
  [string]$Root = "."
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Section([string]$t) {
  Write-Host ""
  Write-Host "============================================================" -ForegroundColor DarkGray
  Write-Host $t -ForegroundColor Cyan
  Write-Host "============================================================" -ForegroundColor DarkGray
}

function Resolve-RepoRoot([string]$r) {
  $p = Resolve-Path $r
  return $p.Path
}

function Test-PortOpen([int]$p) {
  try {
    $conn = Test-NetConnection -ComputerName "127.0.0.1" -Port $p -WarningAction SilentlyContinue
    return [bool]$conn.TcpTestSucceeded
  } catch { return $false }
}

function Start-Server([string]$repoRoot, [int]$p) {
  if (Test-PortOpen $p) {
    Write-Host "Server ya esta arriba en puerto $p (nice)." -ForegroundColor Green
    return
  }

  $logDir = Join-Path $repoRoot "data\run"
  if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }

  $logOut = Join-Path $logDir "control_tower_server.out.log"
  $logErr = Join-Path $logDir "control_tower_server.err.log"

  Write-Host "Levantando server en puerto $p (sin secuestrar tu consola)..." -ForegroundColor Yellow
  $pyArgs = "-m http.server $p --directory `"$repoRoot`""
  Start-Process -FilePath "python" -ArgumentList $pyArgs -WorkingDirectory $repoRoot -WindowStyle Minimized `
    -RedirectStandardOutput $logOut -RedirectStandardError $logErr | Out-Null

  Start-Sleep -Milliseconds 400
  if (Test-PortOpen $p) {
    Write-Host "Server arriba: http://localhost:$p" -ForegroundColor Green
  } else {
    Write-Host "Ojo: no pude confirmar el server. Revisa logs:" -ForegroundColor Red
    Write-Host "  OUT: $logOut" -ForegroundColor Red
    Write-Host "  ERR: $logErr" -ForegroundColor Red
  }
}

function Open-Dashboard([int]$p) {
  $url = "http://localhost:$p/dash/control_tower.html"
  Write-Host "Abriendo: $url" -ForegroundColor Cyan
  Start-Process $url | Out-Null
}

function Read-JsonSafe([string]$path) {
  if (-not (Test-Path $path)) { return $null }
  try {
    $raw = Get-Content $path -Raw -Encoding UTF8
    if (-not $raw) { return $null }
    return ($raw | ConvertFrom-Json)
  } catch {
    return $null
  }
}

function Get-Prop($obj, [string]$path) {
  if ($null -eq $obj) { return $null }
  if ([string]::IsNullOrWhiteSpace($path)) { return $null }
  $cur = $obj
  foreach ($k in ($path -split "\.")) {
    if ($null -eq $cur) { return $null }
    $props = @()
    try { $props = $cur.PSObject.Properties.Name } catch { return $null }
    if ($props -notcontains $k) { return $null }
    $cur = $cur.$k
  }
  return $cur
}

# ----------------------------
# Main
# ----------------------------
$repoRoot = Resolve-RepoRoot $Root
Set-Location $repoRoot

Write-Section "CT OPS  CONTEXT"
Write-Host ("Repo: {0}" -f $repoRoot) -ForegroundColor Cyan

Write-Section "PRE-FLIGHT: ENCODING GUARD"
& python (Join-Path $repoRoot "scripts\check_encoding.py")
if ($LASTEXITCODE -ne 0) {
  Write-Host "Encoding guard FAIL -> abort." -ForegroundColor Red
  exit 1
}

if ($Sim) {
  Write-Section "RUN: SIM PIPELINE"
  & powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts\run_sim_control_tower.ps1")
}

if (-not $NoSnapshot) {
  Write-Section "BUILD: CONTROL TOWER SNAPSHOT (CANON ATOMIC)"
  $out = Join-Path $repoRoot "data\run\control_tower_snapshot.json"
  & python -m synapse.meta.meta_control_tower_snapshot --repo "$repoRoot" --out "$out"
  if ($LASTEXITCODE -ne 0) {
    Write-Host "WARN: snapshot builder fallo (pero seguimos)." -ForegroundColor Yellow
  }
}

Write-Section "CONTROL TOWER  OUTPUTS (SANITY)"
$base = Join-Path $repoRoot "data\run"
$paths = @{
  preflight = (Join-Path $base "meta_publish_preflight.json")
  run       = (Join-Path $base "meta_publish_run.json")
  report    = (Join-Path $base "meta_publish_report.json")
  autopilot = (Join-Path $base "meta_autopilot.json")
  policy    = (Join-Path $base "meta_policy_check.json")
  index     = (Join-Path $base "meta_publish_runs_index.json")
  snapshot  = (Join-Path $base "control_tower_snapshot.json")
}

foreach ($k in $paths.Keys) {
  $exists = Test-Path $paths[$k]
  $mark = if ($exists) { "OK " } else { "MISS" }
  $color = if ($exists) { "Green" } else { "Red" }
  Write-Host ("[{0}] {1}" -f $mark, $paths[$k]) -ForegroundColor $color
}

Write-Section "EXEC SUMMARY (FROM SNAPSHOT)"
$snap = Read-JsonSafe $paths.snapshot
if ($null -eq $snap) {
  Write-Host "Snapshot no cargable. Revisa data/run/control_tower_snapshot.json" -ForegroundColor Yellow
} else {
  $k = $snap.kpis
  Write-Host ("Mode:      {0}" -f $k.mode) -ForegroundColor Cyan
  Write-Host ("Policy:    {0}" -f $k.policy_status) -ForegroundColor Cyan
  Write-Host ("Autopilot: {0}" -f $k.autopilot_health) -ForegroundColor Cyan
  Write-Host ("Runs:      {0}" -f $k.runs_count) -ForegroundColor Cyan
  Write-Host ("Rows/Err:  {0} rows | {1} errors" -f $k.rows, $k.errors) -ForegroundColor Cyan
  Write-Host ("FP12/SHA:  {0} | {1}" -f $k.fp12, $k.sha12) -ForegroundColor Cyan
  Write-Host ("ContentFP: {0}" -f (Get-Prop $snap "freshness.content_fp12")) -ForegroundColor Cyan
}

if ($Serve) { Start-Server $repoRoot $Port }
if ($Open)  { Open-Dashboard $Port }