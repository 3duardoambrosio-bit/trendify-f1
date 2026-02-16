param(
  [string]$OutDir = "artifacts",
  [switch]$Quiet
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Say([string]$s) { if (-not $Quiet) { Write-Host $s } }

function CountLinesFromGitGrep([string[]]$args) {
  $out = & git @args 2>$null
  return @($out).Count
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$outTxt  = Join-Path $OutDir ("evidence_snapshot_{0}.txt" -f $ts)
$outJson = Join-Path $OutDir ("evidence_snapshot_{0}.json" -f $ts)

Say "=== SNAPSHOT OUT ==="
Say $outTxt
Say $outJson

# A) Git state
$gitHead = (git rev-parse --short HEAD).Trim()
$dirtyLines = @(git status --porcelain).Count

# B) Pytest NUMERICO via JUnit XML
$pytestLog   = Join-Path $OutDir ("pytest_{0}.txt" -f $ts)
$pytestJUnit = Join-Path $OutDir ("pytest_{0}.xml" -f $ts)

& python -m pytest -q --junitxml $pytestJUnit | Tee-Object -FilePath $pytestLog | Out-Null
$pytestExit = $LASTEXITCODE

$testsTotal = 0
$failures = 0
$errors = 0
$skipped = 0
$passed = 0
$junitParsed = $false

if (Test-Path $pytestJUnit) {
  try {
    [xml]$x = Get-Content $pytestJUnit -Raw
    $nodes = $x.SelectNodes("//testsuite")
    if ($nodes -and $nodes.Count -gt 0) {
      foreach ($n in $nodes) {
        $testsTotal += [int]$n.GetAttribute("tests")
        $failures   += [int]$n.GetAttribute("failures")
        $errors     += [int]$n.GetAttribute("errors")
        $skipped    += [int]$n.GetAttribute("skipped")
      }
      $passed = $testsTotal - $failures - $errors - $skipped
      if ($passed -lt 0) { $passed = 0 }
      $junitParsed = $true
    }
  } catch { $junitParsed = $false }
}

# C) Doctor (determinista): python captura + parsea OVERALL; PS recibe token
$doctorLog = Join-Path $OutDir ("doctor_{0}.txt" -f $ts)
$env:SYNAPSE_SNAPSHOT_DOCTOR_LOG = $doctorLog

$doctorToken = & python -c "import os,subprocess,sys,re; log=os.environ.get('SYNAPSE_SNAPSHOT_DOCTOR_LOG','doctor.txt'); p=subprocess.run([sys.executable,'-m','synapse.infra.doctor'],capture_output=True,text=True,encoding='utf-8',errors='replace'); txt=(p.stdout or '')+(p.stderr or ''); open(log,'w',encoding='utf-8',newline='\n').write(txt); m=re.search(r'OVERALL:\s+([A-Z]+)',txt); print(m.group(1) if m else 'UNKNOWN'); sys.exit(p.returncode)"
$doctorExit = $LASTEXITCODE

$doctorOverall = "UNKNOWN"
if ($null -ne $doctorToken) {
  $s = ($doctorToken | Select-Object -First 1).ToString().Trim()
  if ($s -match '^[A-Z]+$') { $doctorOverall = $s }
}

# C2) Parse canonical_rows desde doctorLog (fallback)
$canonicalRowsFromDoctor = -1
if (Test-Path $doctorLog) {
  $raw = Get-Content $doctorLog -Raw -Encoding UTF8
  if ($raw -match '(?im)canonical_csv:\s+.*\((\d+)\s+row[s]?\)') {
    $canonicalRowsFromDoctor = [int]$Matches[1]
  }
}

# D) Canonical CSV auto-detect (best-effort)
$canonicalCsv = $null
if (Test-Path ".\data") {
  $cand = Get-ChildItem ".\data" -Recurse -File -Filter "*.csv" |
    Where-Object { $_.Name -match 'canonical' } |
    Select-Object -First 1
  if ($cand) { $canonicalCsv = $cand.FullName }
}

$canonicalRows = -1
if ($null -ne $canonicalCsv -and (Test-Path $canonicalCsv)) {
  try { $canonicalRows = (Import-Csv $canonicalCsv | Measure-Object).Count } catch { $canonicalRows = -2 }
}

# Fallback final: si no encontramos CSV pero doctor sí sabe N rows, usa N
if ($canonicalRows -lt 0 -and $canonicalRowsFromDoctor -ge 0) {
  $canonicalRows = $canonicalRowsFromDoctor
}

$canonicalCsvText = "NOT_FOUND"
if ($null -ne $canonicalCsv -and $canonicalCsv.Trim().Length -gt 0) { $canonicalCsvText = $canonicalCsv }

$canonicalCsvJson = $null
if ($canonicalCsvText -ne "NOT_FOUND") { $canonicalCsvJson = $canonicalCsvText }

# E) Evidence files
$evidenceFiles = -1
if (Test-Path ".\data\evidence") {
  $evidenceFiles = (Get-ChildItem ".\data\evidence" -Recurse -File | Measure-Object).Count
}

# F) Greps
$metaSmartHits = CountLinesFromGitGrep @("grep","-n","smart_promotion_type","--","synapse")
$metaAscHits   = CountLinesFromGitGrep @("grep","-n","AUTOMATED_SHOPPING_ADS","--","synapse")
$idempoHits    = CountLinesFromGitGrep @("grep","-nE","idempot|idempotency|X-Idempotency-Key|InMemoryIdempotencyStore","--","synapse","ops","infra","vault")

# TXT
Add-Content -Path $outTxt -Value "=== SUMMARY ==="
Add-Content -Path $outTxt -Value ("head={0}" -f $gitHead)
Add-Content -Path $outTxt -Value ("dirty_lines={0}" -f $dirtyLines)
Add-Content -Path $outTxt -Value ("pytest_exit={0}" -f $pytestExit)
Add-Content -Path $outTxt -Value ("pytest_junit_parsed={0}" -f $junitParsed)
Add-Content -Path $outTxt -Value ("pytest_total={0}" -f $testsTotal)
Add-Content -Path $outTxt -Value ("pytest_passed={0}" -f $passed)
Add-Content -Path $outTxt -Value ("pytest_failures={0}" -f $failures)
Add-Content -Path $outTxt -Value ("pytest_errors={0}" -f $errors)
Add-Content -Path $outTxt -Value ("pytest_skipped={0}" -f $skipped)
Add-Content -Path $outTxt -Value ("doctor_exit={0}" -f $doctorExit)
Add-Content -Path $outTxt -Value ("doctor_overall={0}" -f $doctorOverall)
Add-Content -Path $outTxt -Value ("canonical_csv={0}" -f $canonicalCsvText)
Add-Content -Path $outTxt -Value ("canonical_rows={0}" -f $canonicalRows)
Add-Content -Path $outTxt -Value ("evidence_files={0}" -f $evidenceFiles)
Add-Content -Path $outTxt -Value ("meta_smart_promotion_type_hits={0}" -f $metaSmartHits)
Add-Content -Path $outTxt -Value ("meta_asc_legacy_hits={0}" -f $metaAscHits)
Add-Content -Path $outTxt -Value ("idempotency_signal_hits={0}" -f $idempoHits)

# JSON
$payload = [ordered]@{
  head = $gitHead
  dirty_lines = $dirtyLines
  pytest = @{
    exit_code = $pytestExit
    junit_parsed = $junitParsed
    total = $testsTotal
    passed = $passed
    failures = $failures
    errors = $errors
    skipped = $skipped
    log = $pytestLog
    junit = $pytestJUnit
  }
  doctor = @{
    exit_code = $doctorExit
    overall = $doctorOverall
    log = $doctorLog
  }
  data = @{
    canonical_csv = $canonicalCsvJson
    canonical_rows = $canonicalRows
    evidence_files = $evidenceFiles
  }
  greps = @{
    meta_smart_promotion_type_hits = $metaSmartHits
    meta_asc_legacy_hits = $metaAscHits
    idempotency_signal_hits = $idempoHits
  }
  created_at = (Get-Date).ToString("o")
}

$payload | ConvertTo-Json -Depth 7 | Set-Content -Path $outJson -Encoding UTF8

Say "=== SUMMARY (NUMERICO) ==="
Say ("head={0} dirty_lines={1} pytest_passed={2}/{3} doctor={4} canonical_rows={5} idempo_hits={6}" -f $gitHead,$dirtyLines,$passed,$testsTotal,$doctorOverall,$canonicalRows,$idempoHits)
exit 0
