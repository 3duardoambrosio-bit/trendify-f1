Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Release Gate (default: seed + canonical)
$ProductId    = "seed"
$CanonicalCsv = "data\catalog\candidates_real.csv"
$OutRoot      = "exports"

function Fail([string]$msg){
  throw $msg
}

function Is-GeneratedPath([string]$pathRaw){
  if(-not $pathRaw){ return $false }
  $p = $pathRaw.Trim().Trim('"') -replace '\\','/'
  # treat all exports as generated artifacts
  if($p -match '^(exports)/'){ return $true }
  # add other generated dirs here if needed
  if($p -match '^(data/run)/'){ return $true }
  return $false
}

function Require-CleanGit(){
  $lines = (git status --porcelain) 2>$null
  if($LASTEXITCODE -ne 0){ Fail "GIT not available / not a repo." }

  $nonGen = @()
  foreach($l in $lines){
    if(-not $l){ continue }
    # porcelain: "XY path"
    $path = ""
    if($l.Length -ge 4){ $path = $l.Substring(3).Trim() }
    if(-not (Is-GeneratedPath $path)){
      $nonGen += $l
    }
  }

  if($nonGen.Count -gt 0){
    Write-Host "DIRTY_TREE (non-generated changes):"
    $nonGen | ForEach-Object { Write-Host $_ }
    Fail "Refusing to release from a dirty working tree (non-generated). Commit or restore changes."
  }
}

function Run-Step([string]$label, [scriptblock]$cmd){
  Write-Host "==> $label"
  & $cmd
  if($LASTEXITCODE -ne 0){
    Fail "$label failed (exit=$LASTEXITCODE). Aborting release."
  }
}

function Parse-HardenSummary([string[]]$lines){
  $hit = $lines | Where-Object { $_ -like "HARDEN_SUMMARY_JSON=*" } | Select-Object -Last 1
  if(-not $hit){ Fail "HARDEN_SUMMARY_JSON not found. harden_wavekit output changed or failed." }
  $json = $hit.Substring("HARDEN_SUMMARY_JSON=".Length)
  try { return ($json | ConvertFrom-Json) } catch { Fail "Failed to parse HARDEN_SUMMARY_JSON as JSON." }
}

Write-Host "============================================================"
Write-Host "WAVEKIT RELEASE GATE (NO API/TOKENS)"
Write-Host "============================================================"
Write-Host ("Repo: {0}" -f (Get-Location))
Write-Host ("ProductId: {0}" -f $ProductId)
Write-Host ("CanonicalCsv: {0}" -f $CanonicalCsv)
Write-Host ("OutRoot: {0}" -f $OutRoot)
Write-Host ""

# 0) Governance gate
Run-Step "git clean guard" { Require-CleanGit }

# 1) Quality gates
Run-Step "pytest" { pytest -q }

Write-Host ""
Run-Step "doctor" { python -m synapse.infra.doctor }

Write-Host ""
Run-Step "wave --apply" { python -m synapse.cli wave --product-id $ProductId --apply --out-root $OutRoot --canonical-csv $CanonicalCsv }

# 2) Harden + validate + produce exports\wave_kit_<product>.zip
Write-Host ""
Write-Host "==> harden_wavekit (STRICT)"
$hardenOut = & python scripts\harden_wavekit.py (Join-Path $OutRoot $ProductId) 2>&1
$hardenExit = $LASTEXITCODE
$hardenOut | ForEach-Object { Write-Host $_ }
if($hardenExit -ne 0){
  Fail "harden_wavekit failed (exit=$hardenExit). Aborting release."
}

$summary = Parse-HardenSummary $hardenOut
if($summary.product_id -ne $ProductId){
  Fail ("ProductId mismatch: summary={0} expected={1}" -f $summary.product_id, $ProductId)
}

# sanity: files exist
$zipPath = ("{0}\wave_kit_{1}.zip" -f $OutRoot, $ProductId)
$shaPath = ("{0}\wave_kit_{1}.sha256" -f $OutRoot, $ProductId)
if(-not (Test-Path $zipPath)){ Fail ("Missing zip: {0}" -f $zipPath) }
if(-not (Test-Path $shaPath)){ Fail ("Missing sha sidecar: {0}" -f $shaPath) }

# 3) Seal release folder by git sha
Write-Host ""
Write-Host "==> seal release dir"
$sha = (git rev-parse --short=12 HEAD).Trim()
$rel = "exports\releases\$ProductId\$sha"
New-Item -ItemType Directory -Force $rel | Out-Null
Copy-Item $zipPath, $shaPath $rel -Force

# 4) Write release meta (provenance) UTF-8 NO BOM
$meta = @{
  git_sha = $sha
  product_id = $ProductId
  canonical_csv = $CanonicalCsv
  out_root = $OutRoot
  harden = $summary
  ts_utc = (Get-Date).ToUniversalTime().ToString("o")
}
$metaPath = Join-Path $rel "release_meta.json"
$metaJson = ($meta | ConvertTo-Json -Depth 10)
[System.IO.File]::WriteAllText($metaPath, $metaJson + "`n", (New-Object System.Text.UTF8Encoding($false)))

Write-Host ("OK RELEASE_DIR={0}" -f $rel)
Write-Host ("OK FILE={0}" -f (Join-Path $rel ("wave_kit_{0}.zip" -f $ProductId)))
Write-Host ("OK SHA ={0}" -f (Join-Path $rel ("wave_kit_{0}.sha256" -f $ProductId)))
Write-Host ("OK META={0}" -f $metaPath)
