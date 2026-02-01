<#  OMEGA_build_opus_audit_pack.ps1  (V2 SAFE)
    - Genera paquete para auditoría externa (Opus):
      * OPUS_PROMPT.txt (prompt + info + código completo embebido)
      * /code (scripts completos)
      * /batch (artefactos: FINAL, manifest, lint, url_audit, report)
      * ZIP final
    - PowerShell 5.1 compatible
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)]
  [string]$Batch,

  [switch]$IncludeGitInfo,
  [switch]$IncludePythonInfo
)

$ErrorActionPreference="Stop"

function _ts { (Get-Date).ToString("HH:mm:ss") }
function Ok([string]$m){ Write-Host ("[{0}]  OK   {1}" -f (_ts), $m) -ForegroundColor Green }
function Warn([string]$m){ Write-Host ("[{0}]  WARN {1}" -f (_ts), $m) -ForegroundColor Yellow }
function Info([string]$m){ Write-Host ("[{0}]       {1}" -f (_ts), $m) -ForegroundColor Gray }
function Die([string]$m){ Write-Host ("[{0}]  FAIL {1}" -f (_ts), $m) -ForegroundColor Red; exit 1 }

function Assert-RepoRoot {
  $need = @(
    ".\scripts\OMEGA_ship_batch.ps1",
    ".\scripts\OMEGA_control_tower.ps1",
    ".\scripts\patch_canonical_images_from_baseurl.py",
    ".\scripts\patch_shopify_images_from_canonical.py",
    ".\scripts\shopify_contract_gate.py"
  )
  foreach ($p in $need) { if (-not (Test-Path $p)) { Die "Falta en repo root: $p" } }
  Ok "repo root OK"
}

function Sha256([string]$p){
  try { return (Get-FileHash -Algorithm SHA256 $p).Hash } catch { return "" }
}

function AppendLine([string]$path, [string]$line){
  $line | Add-Content -Encoding UTF8 $path
}

function AppendBlock([string]$path, [string[]]$lines){
  foreach($l in $lines){ AppendLine $path $l }
}

function Try-Capture([scriptblock]$sb){
  try { return & $sb } catch { return $null }
}

function Copy-IfExists([string]$src,[string]$dst){
  if (Test-Path $src) {
    New-Item -ItemType Directory -Force (Split-Path $dst -Parent) | Out-Null
    Copy-Item -Force $src $dst
    return $true
  }
  return $false
}

function Add-FileEmbed([string]$out,[string]$label,[string]$path){
  AppendLine $out ""
  AppendLine $out ("==============================")
  AppendLine $out ("FILE: " + $label)
  AppendLine $out ("PATH: " + $path)
  if (-not (Test-Path $path)) {
    AppendLine $out "STATUS: MISSING"
    return
  }
  AppendLine $out ("SHA256: " + (Sha256 $path))
  AppendLine $out ("BYTES: " + (Get-Item $path).Length)
  AppendLine $out ("-----BEGIN FILE " + $label + "-----")
  $content = Get-Content $path -Raw
  $content | Add-Content -Encoding UTF8 $out
  AppendLine $out ""
  AppendLine $out ("-----END FILE " + $label + "-----")
}

# ================= RUN =================
Assert-RepoRoot

$batchDir = "exports\releases\_batch\$Batch"
if (-not (Test-Path $batchDir)) { Die "No existe batchDir: $batchDir" }

$stamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
$packName = "OPUS_AUDIT_PACK_{0}_{1}" -f $Batch, $stamp
$packDir  = Join-Path $batchDir $packName

Remove-Item -Recurse -Force $packDir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $packDir | Out-Null

$codeDir  = Join-Path $packDir "code"
$batchOut = Join-Path $packDir "batch"
New-Item -ItemType Directory -Force $codeDir  | Out-Null
New-Item -ItemType Directory -Force $batchOut | Out-Null

$outTxt = Join-Path $packDir "OPUS_PROMPT.txt"
"" | Set-Content -Encoding UTF8 $outTxt

# ---- PROMPT (sin here-string para evitar que se rompa por copy/paste) ----
$promptLines = @(
"ERES OPUS: auditor senior production-grade, red team mindset.",
"",
"OBJETIVO: auditar OMEGA (PS 5.1) que prepara batch para import Shopify SIN APIs.",
"QUIERO que el sistema sea industrial y antifrágil: cero sorpresas, cero 'works on my machine'.",
"",
"ENTREGABLES OBLIGATORIOS EN TU RESPUESTA:",
"A) RED FLAGS (bloqueantes) con evidencia y pasos para reproducir.",
"B) MEJORAS PRIORITIZADAS (P0/P1/P2) con razon de negocio (riesgo/costo).",
"C) PATCH PACK: si propones cambios, entrega ARCHIVOS COMPLETOS listos para copy/paste:",
"   - OMEGA_ship_batch.ps1 completo",
"   - OMEGA_control_tower.ps1 completo",
"   - si aplica: patchers python completos",
"D) PLAN DE PRUEBAS: que probar, como, outputs esperados (incluye red mala).",
"E) HARDENING ROADMAP: subir de 'funciona' a 'empresa seria'.",
"",
"AREAS A AUDITAR SI O SI:",
"1) PowerShell 5.1: switches, backticks, quoting, encoding UTF-8, BOM/no BOM.",
"2) HTTP/Red: HEAD vs GET, redirects, 403/429, timeouts, retry/backoff, TLS12, user-agent.",
"3) Concurrency: runspaces, saturacion, DNS, rate limiting.",
"4) Seguridad: CSV injection, sanitizacion, riesgos de git/publish, exposicion accidental.",
"5) Datos Shopify: handles normalizacion/colisiones, Image Src unicode invisible / esquemas.",
"6) Observabilidad: logs claros, reportes para humanos y maquinas, errores accionables.",
"",
"REGLA: brutalmente honesto y con fixes concretos listos para pegar.",
"",
"NOTA: en este pack viene el codigo completo y los outputs reales del batch."
)

AppendLine  $outTxt "=== OPUS MASTER PROMPT ==="
AppendBlock $outTxt $promptLines
AppendLine  $outTxt ""
AppendLine  $outTxt "=== ENV INFO ==="
AppendLine  $outTxt ("Batch: " + $Batch)
AppendLine  $outTxt ("RepoRoot: " + (Get-Location).Path)
AppendLine  $outTxt ("GeneratedAt: " + (Get-Date).ToString("s"))
AppendLine  $outTxt ("PowerShellVersion: " + $PSVersionTable.PSVersion.ToString())
AppendLine  $outTxt ("CLRVersion: " + $PSVersionTable.CLRVersion.ToString())
AppendLine  $outTxt ("OSVersion: " + [Environment]::OSVersion.ToString())
AppendLine  $outTxt ("MachineName: " + $env:COMPUTERNAME)
AppendLine  $outTxt ("UserName: " + $env:USERNAME)

if ($IncludePythonInfo) {
  AppendLine $outTxt ""
  AppendLine $outTxt "=== PYTHON INFO ==="
  $pyv = Try-Capture { python --version 2>&1 }
  if ($pyv) { AppendLine $outTxt ("python --version: " + (($pyv -join " ").Trim())) } else { AppendLine $outTxt "python --version: (no disponible)" }
  $pys = Try-Capture { python -c "import sys; print(sys.version)" 2>&1 }
  if ($pys) { AppendLine $outTxt ("sys.version: " + (($pys -join " ").Trim())) }
}

if ($IncludeGitInfo) {
  AppendLine $outTxt ""
  AppendLine $outTxt "=== GIT INFO ==="
  $head = Try-Capture { git rev-parse HEAD 2>$null }
  if ($head) { AppendLine $outTxt ("HEAD: " + ($head | Select-Object -First 1)) } else { AppendLine $outTxt "HEAD: (no disponible)" }
  $st = Try-Capture { git status --porcelain 2>$null }
  AppendLine $outTxt "status (porcelain):"
  if ($st) { ($st | Out-String).TrimEnd() | Add-Content -Encoding UTF8 $outTxt } else { AppendLine $outTxt "(no disponible)" }
}

# ---- COPY ARTEFACTOS ----
$finalCsv = Join-Path $batchDir "shopify_import_all.FINAL.csv"
$report   = Join-Path $batchDir "OMEGA_REPORT.json"
$kitDir   = Join-Path $batchDir "IMPORT_KIT"

Copy-IfExists $finalCsv (Join-Path $batchOut "shopify_import_all.FINAL.csv") | Out-Null
Copy-IfExists $report   (Join-Path $batchOut "OMEGA_REPORT.json")           | Out-Null
if (Test-Path $kitDir) {
  Copy-IfExists (Join-Path $kitDir "manifest.json")     (Join-Path $batchOut "manifest.json")     | Out-Null
  Copy-IfExists (Join-Path $kitDir "lint_summary.json") (Join-Path $batchOut "lint_summary.json") | Out-Null
  Copy-IfExists (Join-Path $kitDir "url_audit.csv")     (Join-Path $batchOut "url_audit.csv")     | Out-Null
}

# ---- COPY CODE FILES + EMBED IN PROMPT ----
$files = @(
  @{ label="OMEGA_ship_batch.ps1"; path=".\scripts\OMEGA_ship_batch.ps1" },
  @{ label="OMEGA_control_tower.ps1"; path=".\scripts\OMEGA_control_tower.ps1" },
  @{ label="patch_canonical_images_from_baseurl.py"; path=".\scripts\patch_canonical_images_from_baseurl.py" },
  @{ label="patch_shopify_images_from_canonical.py"; path=".\scripts\patch_shopify_images_from_canonical.py" },
  @{ label="shopify_contract_gate.py"; path=".\scripts\shopify_contract_gate.py" }
)

AppendLine $outTxt ""
AppendLine $outTxt "=== FULL SOURCE CODE (EMBEDDED) ==="

foreach($f in $files){
  $dst = Join-Path $codeDir $f.label
  Copy-IfExists $f.path $dst | Out-Null
  Add-FileEmbed -out $outTxt -label $f.label -path $f.path
}

# ---- ZIP ----
$zip = Join-Path $batchDir ($packName + ".zip")
if (Test-Path $zip) { Remove-Item -Force $zip }
Compress-Archive -Path (Join-Path $packDir "*") -DestinationPath $zip -Force

Ok ("PACK DIR -> " + $packDir)
Ok ("OPUS_PROMPT.txt -> " + $outTxt)
Ok ("ZIP -> " + $zip)
