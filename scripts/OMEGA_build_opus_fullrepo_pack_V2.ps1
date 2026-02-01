<#  OMEGA_build_opus_fullrepo_pack_V2.ps1  (FULL REPO AUDIT PACK  WORKTREE)
    - Pack para auditoría externa (Opus):
      * OPUS_PROMPT.txt
      * /repo_snapshot  (snapshot del repo COMPLETO incluyendo untracked; con exclusiones seguras)
      * /batch          (artefactos reales del batch: FINAL, manifest, lint, url_audit, report)
      * /code_omega     (scripts omega + gates/patchers clave)
      * SECRETS_SCAN.txt (scan heurístico)
      * ZIP final (tar, sin locks)
    - Windows PowerShell 5.1 compatible
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)]
  [string]$Batch,

  [switch]$IncludeGitInfo,
  [switch]$IncludePythonInfo,

  # Normalmente NO (pesa); ya incluimos /batch con outputs reales
  [switch]$IncludeExports
)

$ErrorActionPreference="Stop"

function _ts { (Get-Date).ToString("HH:mm:ss") }
function Ok([string]$m){ Write-Host ("[{0}]  OK   {1}" -f (_ts), $m) -ForegroundColor Green }
function Warn([string]$m){ Write-Host ("[{0}]  WARN {1}" -f (_ts), $m) -ForegroundColor Yellow }
function Info([string]$m){ Write-Host ("[{0}]       {1}" -f (_ts), $m) -ForegroundColor Gray }
function Die([string]$m){ Write-Host ("[{0}]  FAIL {1}" -f (_ts), $m) -ForegroundColor Red; exit 1 }

function Sha256([string]$p){
  try { return (Get-FileHash -Algorithm SHA256 $p).Hash } catch { return "" }
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

function AppendLine([string]$path, [string]$line){
  $line | Add-Content -Encoding UTF8 $path
}

function Assert-RepoRoot {
  if (-not (Test-Path ".\scripts")) { Die "No veo .\scripts. ¿Estás en repo root?" }
  Ok "repo root OK"
}

function Make-RepoSnapshot {
  param(
    [string]$destDir,
    [switch]$includeExports
  )

  New-Item -ItemType Directory -Force $destDir | Out-Null

  $src = (Get-Location).Path
  $dst = Join-Path $destDir "repo"
  New-Item -ItemType Directory -Force $dst | Out-Null

  $xd = @(".git",".svn",".hg",".idea",".vscode","__pycache__", ".pytest_cache",".mypy_cache",".ruff_cache",".cache",
          ".venv","venv","env","node_modules","dist","build",".next","out",".DS_Store")
  if (-not $includeExports) { $xd += @("exports") }

  $xf = @("*.pem","*.key","*.pfx","*.p12","id_rsa","id_rsa.pub",".env",".env.*","*.sqlite","*.db","*.log")

  Info "Repo snapshot via filesystem (robocopy). IncludeExports=$includeExports"
  $cmd = @("robocopy", $src, $dst, "/MIR", "/R:1", "/W:1", "/NFL", "/NDL", "/NP", "/XJ")
  foreach($d in $xd){ $cmd += @("/XD", (Join-Path $src $d)) }
  foreach($f in $xf){ $cmd += @("/XF", $f) }

  & $cmd[0] $cmd[1..($cmd.Count-1)] | Out-Null
  $rc = $LASTEXITCODE

  # Robocopy: 0-7 = OK, >=8 = fail
  if ($rc -ge 8) { Die "robocopy falló con exit code $rc" }

  Ok "filesystem snapshot OK -> $dst"
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
        $m = Select-String -Path $f.FullName -Pattern $p -ErrorAction SilentlyContinue
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

function Write-OpusPrompt {
  param(
    [string]$outTxt,
    [string]$batchDir,
    [string]$packDir
  )

  "" | Set-Content -Encoding UTF8 $outTxt

  AppendLine $outTxt "=== OPUS MASTER PROMPT ==="
  AppendLine $outTxt "Eres OPUS (auditor senior, production-grade, mentalidad red-team)."
  AppendLine $outTxt ""
  AppendLine $outTxt "OBJETIVO: Audita TODO el sistema del repo (arquitectura + calidad + seguridad + operabilidad), y además el pipeline OMEGA que genera CSVs para importar en Shopify SIN APIs."
  AppendLine $outTxt ""
  AppendLine $outTxt "TE ADJUNTO UN ZIP. Dentro viene:"
  AppendLine $outTxt "- /repo_snapshot/repo  => snapshot completo del repo (incluye untracked; con exclusiones seguras)."
  AppendLine $outTxt "- /batch              => outputs reales del batch (FINAL CSV, manifest, lint, url_audit, report)."
  AppendLine $outTxt "- /code_omega          => scripts omega/gates/patchers clave como referencia rápida."
  AppendLine $outTxt "- SECRETS_SCAN.txt     => scan heurístico (no perfecto) de patrones peligrosos."
  AppendLine $outTxt ""
  AppendLine $outTxt "ENTREGABLES OBLIGATORIOS (en tu respuesta):"
  AppendLine $outTxt "A) RED FLAGS (bloqueantes) con evidencia y reproducción (comandos exactos)."
  AppendLine $outTxt "B) MEJORAS priorizadas P0/P1/P2 con razón de negocio (riesgo/costo)."
  AppendLine $outTxt "C) PATCH PACK: si propones cambios, entrega ARCHIVOS COMPLETOS listos para copiar/pegar (no diffs)."
  AppendLine $outTxt "D) PLAN DE PRUEBAS: qué probar, cómo, outputs esperados (incluye red mala: 403/429/timeouts/CDN que bloquea HEAD)."
  AppendLine $outTxt "E) HARDENING ROADMAP: observabilidad, idempotencia, retries/backoff, fallback HEAD->GET, seguridad, UX operador."
  AppendLine $outTxt ""
  AppendLine $outTxt "ÁREAS QUE DEBES AUDITAR SÍ O SÍ:"
  AppendLine $outTxt "1) Arquitectura del repo: módulos, acoplamientos, deuda técnica, puntos frágiles."
  AppendLine $outTxt "2) PowerShell 5.1: quoting/backticks, encoding UTF-8, errores accionables, idempotencia."
  AppendLine $outTxt "3) HTTP/Red: HEAD vs GET, redirects, 403/429, timeouts, retry/backoff, TLS12, user-agent."
  AppendLine $outTxt "4) Concurrency: runspaces/backpressure/leaks/disposal."
  AppendLine $outTxt "5) Seguridad: CSV injection, sanitización, no filtrar secretos, publicación accidental de assets."
  AppendLine $outTxt "6) Datos Shopify: handles colisiones/normalización, Image Src unicode invisible/esquemas."
  AppendLine $outTxt "7) Observabilidad: reportes legibles por humanos y máquinas (JSON contracts)."
  AppendLine $outTxt ""
  AppendLine $outTxt "REGLA: Brutalmente honesto y CON FIXES CONCRETOS."
  AppendLine $outTxt ""
  AppendLine $outTxt "=== ENV INFO ==="
  AppendLine $outTxt ("Batch: " + $Batch)
  AppendLine $outTxt ("RepoRoot: " + (Get-Location).Path)
  AppendLine $outTxt ("BatchDir: " + $batchDir)
  AppendLine $outTxt ("PackDir: " + $packDir)
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
}

function Zip-WithTar {
  param([string]$packDir,[string]$zipPath)

  $tar = Get-Command tar -ErrorAction SilentlyContinue
  if (-not $tar) { Die "No encuentro 'tar' en el sistema. (Windows moderno sí lo trae)" }

  if (Test-Path $zipPath) { Remove-Item -Force $zipPath }

  Info "Creando ZIP con tar (anti-lock)..."
  & tar -a -c -f $zipPath -C $packDir . | Out-Null

  if (-not (Test-Path $zipPath)) { Die "No se creó el zip: $zipPath" }
  Ok "ZIP OK -> $zipPath"
}

# ================= RUN =================
Assert-RepoRoot

$batchDir = "exports\releases\_batch\$Batch"
if (-not (Test-Path $batchDir)) { Die "No existe batchDir: $batchDir" }

$stamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
$packName = "OPUS_AUDIT_FULLREPO_WORKTREE_{0}_{1}" -f $Batch, $stamp
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
Write-OpusPrompt -outTxt $outTxt -batchDir $batchDir -packDir $packDir

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

# ---- COPIAR scripts clave omega (rápido acceso) ----
$keys = Get-ChildItem ".\scripts" -File -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -match "^(OMEGA_|patch_|shopify_|canonical_|release_|probe_|hunt_).*\.(ps1|py)$" }

foreach($f in $keys){
  Copy-Item -Force $f.FullName (Join-Path $omegaDir $f.Name)
}

# ---- SNAPSHOT DEL REPO COMPLETO (WORKTREE) ----
Info "Generando snapshot FULL repo (worktree)..."
Make-RepoSnapshot -destDir $repoSnap -includeExports:$IncludeExports

# ---- SCAN BASICO DE SECRETOS ----
$scan = Join-Path $packDir "SECRETS_SCAN.txt"
Info "Corriendo scan heurístico de secretos..."
Secrets-Scan -repoDir (Join-Path $repoSnap "repo") -outFile $scan
Ok "SECRETS_SCAN.txt OK"

# ---- ZIP FINAL SEND_TO_OPUS ----
$zip = Join-Path $batchDir ("SEND_TO_OPUS_FULLREPO_WORKTREE_{0}_{1}.zip" -f $Batch, $stamp)
Zip-WithTar -packDir $packDir -zipPath $zip

Ok ("PACK DIR -> " + $packDir)
Ok ("OPUS_PROMPT.txt -> " + $outTxt)
Ok ("SEND ZIP -> " + $zip)
