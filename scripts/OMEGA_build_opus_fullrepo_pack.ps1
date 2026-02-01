<#  OMEGA_build_opus_fullrepo_pack.ps1  (V3 NO-LOCK)
    - FULL REPO AUDIT PACK para Opus:
      * OPUS_PROMPT.txt
      * /repo_snapshot/files (repo completo extraído, sin ZIP anidado)
      * /batch (FINAL, manifest, lint, url_audit, report)
      * /code_omega (scripts Omega + patchers)
      * SECRETS_SCAN.txt (scan heurístico)
      * ZIP final
    - PowerShell 5.1 compatible
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)]
  [string]$Batch,

  [switch]$IncludeGitInfo,
  [switch]$IncludePythonInfo,
  [switch]$IncludeExports
)

$ErrorActionPreference="Stop"

function _ts { (Get-Date).ToString("HH:mm:ss") }
function Ok([string]$m){ Write-Host ("[{0}]  OK   {1}" -f (_ts), $m) -ForegroundColor Green }
function Warn([string]$m){ Write-Host ("[{0}]  WARN {1}" -f (_ts), $m) -ForegroundColor Yellow }
function Info([string]$m){ Write-Host ("[{0}]       {1}" -f (_ts), $m) -ForegroundColor Gray }
function Die([string]$m){ Write-Host ("[{0}]  FAIL {1}" -f (_ts), $m) -ForegroundColor Red; exit 1 }

function Try-Capture([scriptblock]$sb){
  try { return & $sb } catch { return $null }
}

function Sha256([string]$p){
  try { return (Get-FileHash -Algorithm SHA256 $p).Hash } catch { return "" }
}

function Copy-IfExists([string]$src,[string]$dst){
  if (Test-Path $src) {
    New-Item -ItemType Directory -Force (Split-Path $dst -Parent) | Out-Null
    Copy-Item -Force $src $dst
    return $true
  }
  return $false
}

function AppendLine([string]$path, [string]$line){
  $line | Add-Content -Encoding UTF8 $path
}

function Add-FileEmbed([string]$out,[string]$label,[string]$path){
  AppendLine $out ""
  AppendLine $out ("==============================")
  AppendLine $out ("FILE: " + $label)
  AppendLine $out ("PATH: " + $path)
  if (-not (Test-Path $path)) { AppendLine $out "STATUS: MISSING"; return }
  AppendLine $out ("SHA256: " + (Sha256 $path))
  AppendLine $out ("BYTES: " + (Get-Item $path).Length)
  AppendLine $out ("-----BEGIN FILE " + $label + "-----")
  (Get-Content $path -Raw) | Add-Content -Encoding UTF8 $out
  AppendLine $out ""
  AppendLine $out ("-----END FILE " + $label + "-----")
}

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

function Retry-IO {
  param(
    [string]$Label,
    [scriptblock]$Action,
    [int]$Retries = 12,
    [int]$SleepMs = 250
  )
  for($i=1; $i -le $Retries; $i++){
    try {
      return & $Action
    } catch {
      if ($i -eq $Retries) { throw }
      Start-Sleep -Milliseconds $SleepMs
    }
  }
}

function Make-RepoSnapshot {
  param(
    [string]$destDir,
    [switch]$includeExports
  )

  New-Item -ItemType Directory -Force $destDir | Out-Null

  $isGit = $false
  $gitOk = Try-Capture { git --version 2>$null }
  if ($gitOk -and (Test-Path ".\.git")) {
    $inside = Try-Capture { git rev-parse --is-inside-work-tree 2>$null }
    if ($inside -and ($inside | Select-Object -First 1) -match "true") { $isGit = $true }
  }

  if ($isGit) {
    Info "Repo snapshot via git archive -> extract (NO ZIP nested)."
    $tmpZip = Join-Path $env:TEMP ("repo_snapshot_{0}.zip" -f ([guid]::NewGuid().ToString("N")))
    $filesDir = Join-Path $destDir "files"
    New-Item -ItemType Directory -Force $filesDir | Out-Null

    & git archive --format=zip -o $tmpZip HEAD | Out-Null

    Retry-IO -Label "Expand-Archive repo snapshot" -Action {
      Expand-Archive -Path $tmpZip -DestinationPath $filesDir -Force
    } | Out-Null

    Remove-Item -Force $tmpZip -ErrorAction SilentlyContinue
    Ok "git snapshot extracted -> $filesDir"
    return $filesDir
  }

  Warn "No git archive disponible. Snapshot por filesystem (robocopy) con exclusiones."
  $xd = @(".git",".svn",".hg",".idea",".vscode","__pycache__", ".pytest_cache",".mypy_cache",".ruff_cache",".cache",
          ".venv","venv","env","node_modules","dist","build",".next","out",".DS_Store")
  if (-not $includeExports) { $xd += @("exports") }

  $xf = @("*.pem","*.key","*.pfx","*.p12","id_rsa","id_rsa.pub",".env",".env.*","*.sqlite","*.db","*.log")

  $src = (Get-Location).Path
  $cmd = @("robocopy", $src, $destDir, "/MIR", "/R:1", "/W:1", "/NFL", "/NDL", "/NP")
  foreach($d in $xd){ $cmd += @("/XD", (Join-Path $src $d)) }
  foreach($f in $xf){ $cmd += @("/XF", $f) }

  & $cmd[0] $cmd[1..($cmd.Count-1)] | Out-Null
  Ok "filesystem snapshot OK -> $destDir"
  return $destDir
}

function Secrets-Scan {
  param([string]$repoDir, [string]$outFile)

  "" | Set-Content -Encoding UTF8 $outFile
  AppendLine $outFile "SECRETS_SCAN (heuristico, no perfecto)"
  AppendLine $outFile ("GeneratedAt: " + (Get-Date).ToString("s"))
  AppendLine $outFile ""

  $patterns = @(
    "BEGIN PRIVATE KEY",
    "BEGIN RSA PRIVATE KEY",
    "api[_-]?key",
    "secret",
    "token",
    "password",
    "authorization:\s*bearer",
    "x-api-key",
    "aws_access_key_id",
    "aws_secret_access_key",
    "shopify",
    "openai"
  )

  $files = Get-ChildItem -Path $repoDir -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object {
      $_.Length -lt 5MB -and
      $_.FullName -notmatch "\\node_modules\\|\\dist\\|\\build\\|\\\.git\\"
    }

  foreach($p in $patterns){
    AppendLine $outFile ("--- PATTERN: " + $p)
    $hits = @()
    foreach($f in $files){
      try {
        $m = Select-String -Path $f.FullName -Pattern $p -SimpleMatch:$false -ErrorAction SilentlyContinue
        if ($m) { $hits += $m }
      } catch {}
    }
    if (-not $hits -or $hits.Count -eq 0) {
      AppendLine $outFile "OK: no hits"
    } else {
      AppendLine $outFile ("HITS: " + $hits.Count)
      $hits | Select-Object -First 200 | ForEach-Object {
        AppendLine $outFile ("- " + $_.Path + ":" + $_.LineNumber + " :: " + ($_.Line.Trim()))
      }
    }
    AppendLine $outFile ""
  }
}

# ================= RUN =================
Assert-RepoRoot

$batchDir = "exports\releases\_batch\$Batch"
if (-not (Test-Path $batchDir)) { Die "No existe batchDir: $batchDir" }

$stamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
$packName = "OPUS_AUDIT_FULLREPO_{0}_{1}" -f $Batch, $stamp
$packDir  = Join-Path $batchDir $packName

Remove-Item -Recurse -Force $packDir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $packDir | Out-Null

$repoSnap = Join-Path $packDir "repo_snapshot"
$batchOut = Join-Path $packDir "batch"
$omegaDir = Join-Path $packDir "code_omega"
New-Item -ItemType Directory -Force $repoSnap | Out-Null
New-Item -ItemType Directory -Force $batchOut | Out-Null
New-Item -ItemType Directory -Force $omegaDir | Out-Null

$outTxt = Join-Path $packDir "OPUS_PROMPT.txt"
"" | Set-Content -Encoding UTF8 $outTxt

# ---- PROMPT ----
$prompt = @(
"ERES OPUS: auditor senior production-grade, red team mindset.",
"",
"QUIERO que audites TODO el sistema del repositorio (repo completo), no solo un script.",
"Te adjunto un ZIP con snapshot del repo + outputs reales del batch + scripts clave.",
"",
"OBJETIVO: convertir este sistema en industrial y antifragil (cero sorpresas, cero works-on-my-machine).",
"",
"ENTREGABLES OBLIGATORIOS:",
"A) RED FLAGS (bloqueantes) con evidencia + reproduccion.",
"B) MEJORAS P0/P1/P2 con razon de negocio (riesgo/costo).",
"C) PATCH PACK: cuando propongas cambios, entrega ARCHIVOS COMPLETOS listos para copy/paste.",
"D) PLAN DE PRUEBAS: comandos y outputs esperados (incluye red mala, timeouts, 429, 403, CDN que bloquea HEAD).",
"E) HARDENING ROADMAP: observabilidad, idempotencia, retries/backoff, fallback HEAD->GET, seguridad, UX operador.",
"",
"AREAS A AUDITAR SI O SI:",
"1) Arquitectura general del repo: modulos, acoplamientos, puntos fragiles, deuda tecnica.",
"2) PowerShell 5.1: switches/backticks/quoting/encoding/errores accionables.",
"3) HTTP/Red: HEAD vs GET, redirects, 403/429, timeouts, TLS12, rate limiting, cache-buster.",
"4) Concurrency: runspaces, saturacion, leaks, disposal, backpressure.",
"5) Seguridad: CSV injection, sanitizacion, no filtrar secretos, riesgo de publicar assets sin querer.",
"6) Datos/Shopify: handles (normalizacion/colisiones), Image Src unicode invisible/esquemas.",
"7) Observabilidad: logs consistentes, reportes para humanos y maquinas.",
"",
"REGLA: brutalmente honesto y con FIXES concretos listos para pegar.",
"",
"INSTRUCCION DE LECTURA:",
"1) Lee /batch para ver outputs reales.",
"2) Luego audita /repo_snapshot/files (repo completo).",
"3) Usa /code_omega como referencia directa a pipeline actual."
)

AppendLine $outTxt "=== OPUS MASTER PROMPT ==="
foreach($l in $prompt){ AppendLine $outTxt $l }

AppendLine $outTxt ""
AppendLine $outTxt "=== ENV INFO ==="
AppendLine $outTxt ("Batch: " + $Batch)
AppendLine $outTxt ("RepoRoot: " + (Get-Location).Path)
AppendLine $outTxt ("GeneratedAt: " + (Get-Date).ToString("s"))
AppendLine $outTxt ("PowerShellVersion: " + $PSVersionTable.PSVersion.ToString())
AppendLine $outTxt ("CLRVersion: " + $PSVersionTable.CLRVersion.ToString())
AppendLine $outTxt ("OSVersion: " + [Environment]::OSVersion.ToString())
AppendLine $outTxt ("MachineName: " + $env:COMPUTERNAME)

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

# ---- COPIAR OUTPUTS REALES DEL BATCH ----
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

# ---- COPIAR OMEGA FILES CLAVE + EMBED ----
$omegaFiles = @(
  @{ label="OMEGA_ship_batch.ps1"; path=".\scripts\OMEGA_ship_batch.ps1" },
  @{ label="OMEGA_control_tower.ps1"; path=".\scripts\OMEGA_control_tower.ps1" },
  @{ label="patch_canonical_images_from_baseurl.py"; path=".\scripts\patch_canonical_images_from_baseurl.py" },
  @{ label="patch_shopify_images_from_canonical.py"; path=".\scripts\patch_shopify_images_from_canonical.py" },
  @{ label="shopify_contract_gate.py"; path=".\scripts\shopify_contract_gate.py" }
)

AppendLine $outTxt ""
AppendLine $outTxt "=== OMEGA CORE FILES (EMBEDDED) ==="
foreach($f in $omegaFiles){
  Copy-IfExists $f.path (Join-Path $omegaDir $f.label) | Out-Null
  Add-FileEmbed -out $outTxt -label $f.label -path $f.path
}

# ---- SNAPSHOT DEL REPO COMPLETO (sin ZIP anidado) ----
Info "Generando snapshot del repo completo..."
$scanTarget = Make-RepoSnapshot -destDir $repoSnap -includeExports:$IncludeExports

# ---- SCAN BASICO DE SECRETOS ----
$scan = Join-Path $packDir "SECRETS_SCAN.txt"
Info "Corriendo scan heuristico de secretos..."
Secrets-Scan -repoDir $scanTarget -outFile $scan
Ok "SECRETS_SCAN.txt OK"

# ---- ZIP FINAL (con retry) ----
$zip = Join-Path $batchDir ($packName + ".zip")
if (Test-Path $zip) { Remove-Item -Force $zip }

Retry-IO -Label "Compress-Archive final pack" -Action {
  Compress-Archive -Path (Join-Path $packDir "*") -DestinationPath $zip -Force
} | Out-Null

Ok ("PACK DIR -> " + $packDir)
Ok ("OPUS_PROMPT.txt -> " + $outTxt)
Ok ("ZIP -> " + $zip)
