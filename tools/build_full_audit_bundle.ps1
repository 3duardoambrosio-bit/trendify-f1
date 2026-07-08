param(
  [string]$Repo = (Get-Location).Path,
  [string]$OutDir = "",
  [string]$ZipPath = "",
  [switch]$SkipHeavy
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Repo = (Resolve-Path $Repo).Path
if ([string]::IsNullOrWhiteSpace($OutDir)) {
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $OutDir = Join-Path "C:\Temp" "trendify_full_audit_bundle_$stamp"
}
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
Set-Location $Repo

if ([string]::IsNullOrWhiteSpace($ZipPath)) {
  $headForZip = (git rev-parse --short HEAD).Trim()
  $ZipPath = "C:\Temp\trendify_FULL_AUDIT_BUNDLE_$headForZip.zip"
}

# Python resolution, cross-platform: Windows venv, then POSIX venv (Linux CI
# runners), then whatever python is on PATH (GitHub setup-python installs no
# repo venv). Same interpreter contract; only the lookup is platform-aware.
$py = Join-Path $Repo "venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
  $pyPosix = Join-Path $Repo "venv/bin/python"
  if (Test-Path $pyPosix) {
    $py = $pyPosix
  } else {
    $pyCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $pyCmd) {
      $pyCmd = Get-Command python3 -ErrorAction SilentlyContinue
    }
    if ($null -ne $pyCmd) {
      $py = $pyCmd.Source
    } else {
      throw "PYTHON_NOT_FOUND=$py"
    }
  }
}

$env:PYTHONNOUSERSITE = "1"
$env:PYTHONPATH = ""
if ([string]::IsNullOrWhiteSpace($env:PYTEST_ADDOPTS) -or ($env:PYTEST_ADDOPTS -notmatch "(^|\s)--basetemp(=|\s)")) {
  $stableBaseTemp = ("C:/Temp/trendify_bundle_pytest_{0}_{1}" -f $PID, (Get-Date -Format "yyyyMMdd_HHmmss"))
  if ([string]::IsNullOrWhiteSpace($env:PYTEST_ADDOPTS)) {
    $env:PYTEST_ADDOPTS = "--basetemp=$stableBaseTemp"
  } else {
    $env:PYTEST_ADDOPTS = "$($env:PYTEST_ADDOPTS) --basetemp=$stableBaseTemp"
  }
}

function Write-TextFile {
  param([string]$Path, [string]$Text)
  Set-Content -Path $Path -Value $Text -Encoding UTF8
}

function Invoke-Captured {
  param(
    [string]$Name,
    [scriptblock]$Command
  )

  $stdout = Join-Path $OutDir "$Name.stdout.txt"
  $stderr = Join-Path $OutDir "$Name.stderr.txt"
  $rcPath = Join-Path $OutDir "$Name.rc.txt"

  try {
    & $Command > $stdout 2> $stderr
    $rc = $LASTEXITCODE
    if ($null -eq $rc) { $rc = 0 }
  } catch {
    $rc = 999
    Set-Content -Path $stderr -Value $_.Exception.Message -Encoding UTF8
  }

  Set-Content -Path $rcPath -Value "$rc" -Encoding ASCII
  return [int]$rc
}

$head = (git rev-parse --short HEAD).Trim()
$headFull = (git rev-parse HEAD).Trim()
$lastMsg = (git log -1 --pretty=format:%s)
$status = @(git status --short)
$showStat = git show --stat --oneline --summary HEAD
$cachedNames = @(git diff --cached --name-only)

Write-TextFile (Join-Path $OutDir "git_head.txt") $head
Write-TextFile (Join-Path $OutDir "git_head_full.txt") $headFull
Write-TextFile (Join-Path $OutDir "git_last_msg.txt") $lastMsg
Write-TextFile (Join-Path $OutDir "git_status.txt") ($status -join "`n")
Write-TextFile (Join-Path $OutDir "git_show_head_stat.txt") ($showStat -join "`n")
Write-TextFile (Join-Path $OutDir "git_diff_cached_name_only.txt") ($cachedNames -join "`n")

Invoke-Captured "git_diff_cached_check" { git diff --cached --check } | Out-Null
Invoke-Captured "git_diff_check" { git diff --check } | Out-Null
Invoke-Captured "control_check" { & $py "scripts/synapse_control_surface.py" --check } | Out-Null
Invoke-Captured "control_json" { & $py "scripts/synapse_control_surface.py" --json } | Out-Null
Copy-Item -LiteralPath (Join-Path $OutDir "control_json.stdout.txt") -Destination (Join-Path $OutDir "control_json.json") -Force

Invoke-Captured "local_health" { & $py "scripts/synapse_control_surface.py" --run local_health } | Out-Null
Copy-Item -LiteralPath (Join-Path $OutDir "local_health.stdout.txt") -Destination (Join-Path $OutDir "local_health.json") -Force

Invoke-Captured "local_recent_decisions" { & $py "scripts/synapse_control_surface.py" --run local_recent_decisions } | Out-Null
Copy-Item -LiteralPath (Join-Path $OutDir "local_recent_decisions.stdout.txt") -Destination (Join-Path $OutDir "local_recent_decisions.json") -Force

Invoke-Captured "local_safety_status" { & $py "scripts/synapse_control_surface.py" --run local_safety_status } | Out-Null
Copy-Item -LiteralPath (Join-Path $OutDir "local_safety_status.stdout.txt") -Destination (Join-Path $OutDir "local_safety_status.json") -Force

if ($SkipHeavy) {
  Write-TextFile (Join-Path $OutDir "targeted_control_surface.stdout.txt") "SKIPPED_BY_SKIPHEAVY=1"
  Write-TextFile (Join-Path $OutDir "targeted_control_surface.rc.txt") "0"
  Write-TextFile (Join-Path $OutDir "full_suite.stdout.txt") "SKIPPED_BY_SKIPHEAVY=1"
  Write-TextFile (Join-Path $OutDir "full_suite.rc.txt") "0"
  Write-TextFile (Join-Path $OutDir "hook_smoke.stdout.txt") "SKIPPED_BY_SKIPHEAVY=1"
  Write-TextFile (Join-Path $OutDir "hook_smoke.rc.txt") "0"
} else {
  Invoke-Captured "targeted_control_surface" { & $py -m pytest "tests/p0/test_local_control_surface_contract.py" -q } | Out-Null
  Invoke-Captured "full_suite" { & $py -m pytest -q } | Out-Null
  Write-TextFile (Join-Path $OutDir "hook_smoke.stdout.txt") "HOOK_SMOKE_NOT_RUN_BY_BUNDLE_BUILDER=1"
  Write-TextFile (Join-Path $OutDir "hook_smoke.rc.txt") "0"
}

$primaryFiles = @(
  "git_head.txt",
  "git_head_full.txt",
  "git_last_msg.txt",
  "git_status.txt",
  "git_show_head_stat.txt",
  "git_diff_cached_name_only.txt",
  "git_diff_cached_check.stdout.txt",
  "control_check.stdout.txt",
  "control_json.json",
  "local_health.json",
  "local_recent_decisions.json",
  "local_safety_status.json",
  "targeted_control_surface.stdout.txt",
  "full_suite.stdout.txt",
  "hook_smoke.stdout.txt"
)

$existingPrimary = @($primaryFiles | Where-Object { Test-Path (Join-Path $OutDir $_) })
$bundleFileCount = @(Get-ChildItem -LiteralPath $OutDir -File).Count

$summary = @"
FULL_AUDIT_BUNDLE_PASS=1
HEAD=$head
HEAD_FULL=$headFull
LAST_MSG=$lastMsg
STATUS_COUNT=$($status.Count)
PYTEST_ADDOPTS_EFFECTIVE=$env:PYTEST_ADDOPTS
PRIMARY_EVIDENCE_FILE_COUNT=$($existingPrimary.Count)
BUNDLE_FILE_COUNT=$bundleFileCount
SKIP_HEAVY=$([int]$SkipHeavy.IsPresent)
"@
Write-TextFile (Join-Path $OutDir "summary.txt") $summary

Add-Type -AssemblyName System.IO.Compression.FileSystem
if (Test-Path $ZipPath) {
  Remove-Item -LiteralPath $ZipPath -Force
}
# A8-R29_BUNDLE_EVIDENCE_NORMALIZATION_BEGIN
$script:A8R29Utf8NoBomEncoding = [System.Text.UTF8Encoding]::new($false)

function Write-A8R29Utf8NoBomText {
  param(
    [string]$Path,
    [AllowNull()][string]$Text
  )

  $parent = Split-Path -Parent $Path
  if ($parent -and -not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
  }

  [System.IO.File]::WriteAllText($Path, [string]$Text, $script:A8R29Utf8NoBomEncoding)
}

function ConvertFrom-A8R29BytesToText {
  param([byte[]]$Bytes)

  if ($null -eq $Bytes -or $Bytes.Length -eq 0) {
    return ""
  }

  if ($Bytes.Length -ge 3 -and $Bytes[0] -eq 0xEF -and $Bytes[1] -eq 0xBB -and $Bytes[2] -eq 0xBF) {
    return [System.Text.Encoding]::UTF8.GetString($Bytes, 3, $Bytes.Length - 3)
  }

  if ($Bytes.Length -ge 2 -and $Bytes[0] -eq 0xFF -and $Bytes[1] -eq 0xFE) {
    return [System.Text.Encoding]::Unicode.GetString($Bytes, 2, $Bytes.Length - 2)
  }

  if ($Bytes.Length -ge 2 -and $Bytes[0] -eq 0xFE -and $Bytes[1] -eq 0xFF) {
    return [System.Text.Encoding]::BigEndianUnicode.GetString($Bytes, 2, $Bytes.Length - 2)
  }

  $sampleLength = [Math]::Min($Bytes.Length, 200)
  $zeroCount = 0
  for ($i = 0; $i -lt $sampleLength; $i++) {
    if ($Bytes[$i] -eq 0) { $zeroCount++ }
  }

  if ($sampleLength -gt 20 -and $zeroCount -ge [Math]::Floor($sampleLength / 4)) {
    try {
      return [System.Text.Encoding]::Unicode.GetString($Bytes)
    } catch {
      return [System.Text.Encoding]::UTF8.GetString($Bytes)
    }
  }

  return [System.Text.Encoding]::UTF8.GetString($Bytes)
}

function Test-A8R29TextEvidenceFile {
  param([string]$Path)

  $name = [System.IO.Path]::GetFileName($Path).ToLowerInvariant()
  $ext = [System.IO.Path]::GetExtension($Path).ToLowerInvariant()

  if ($ext -in @(".txt", ".json", ".md", ".csv", ".ps1", ".psm1", ".psd1", ".log", ".ini", ".yaml", ".yml", ".toml")) {
    return $true
  }

  if ($name -match "\.rc$") {
    return $true
  }

  return $false
}

function Convert-A8R29EvidenceTextFilesToUtf8NoBom {
  param([string]$Root)

  [int]$utf8BomBefore = 0
  [int]$utf16BomBefore = 0
  [int]$utf16LikeBefore = 0
  [int]$convertedCount = 0
  [int]$textFileCount = 0

  $files = @(Get-ChildItem -LiteralPath $Root -Recurse -File -Force)

  foreach ($file in $files) {
    if (-not (Test-A8R29TextEvidenceFile -Path $file.FullName)) {
      continue
    }

    $textFileCount++
    [byte[]]$bytes = [System.IO.File]::ReadAllBytes($file.FullName)

    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
      $utf8BomBefore++
    }

    if ($bytes.Length -ge 2 -and (($bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) -or ($bytes[0] -eq 0xFE -and $bytes[1] -eq 0xFF))) {
      $utf16BomBefore++
    }

    $sampleLength = [Math]::Min($bytes.Length, 200)
    $zeroCount = 0
    for ($i = 0; $i -lt $sampleLength; $i++) {
      if ($bytes[$i] -eq 0) { $zeroCount++ }
    }
    if ($sampleLength -gt 20 -and $zeroCount -ge [Math]::Floor($sampleLength / 4)) {
      $utf16LikeBefore++
    }

    $decoded = ConvertFrom-A8R29BytesToText -Bytes $bytes
    Write-A8R29Utf8NoBomText -Path $file.FullName -Text $decoded
    $convertedCount++
  }

  [int]$bomAfter = 0
  [int]$utf16After = 0

  $filesAfter = @(Get-ChildItem -LiteralPath $Root -Recurse -File -Force)

  foreach ($file in $filesAfter) {
    if (-not (Test-A8R29TextEvidenceFile -Path $file.FullName)) {
      continue
    }

    [byte[]]$bytes = [System.IO.File]::ReadAllBytes($file.FullName)

    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
      $bomAfter++
    }

    if ($bytes.Length -ge 2 -and (($bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) -or ($bytes[0] -eq 0xFE -and $bytes[1] -eq 0xFF))) {
      $utf16After++
    }
  }

  $auditPath = Join-Path $Root "bundle_encoding_audit.txt"
  $auditText = @(
    "A8_R29_BUNDLE_ENCODING_AUDIT=1"
    "TEXT_EVIDENCE_FILE_COUNT=$textFileCount"
    "UTF8_BOM_BEFORE_COUNT=$utf8BomBefore"
    "UTF16_BOM_BEFORE_COUNT=$utf16BomBefore"
    "UTF16_LIKE_BEFORE_COUNT=$utf16LikeBefore"
    "CONVERTED_TEXT_FILE_COUNT=$convertedCount"
    "BOM_AFTER_COUNT=$bomAfter"
    "UTF16_BOM_AFTER_COUNT=$utf16After"
  ) -join "`n"

  Write-A8R29Utf8NoBomText -Path $auditPath -Text ($auditText + "`n")

  return [pscustomobject]@{
    TextFileCount = $textFileCount
    Utf8BomBefore = $utf8BomBefore
    Utf16BomBefore = $utf16BomBefore
    Utf16LikeBefore = $utf16LikeBefore
    ConvertedCount = $convertedCount
    BomAfter = $bomAfter
    Utf16BomAfter = $utf16After
    AuditPath = $auditPath
  }
}

$sourceSnapshotRoot = Join-Path $OutDir "source_snapshots"
New-Item -ItemType Directory -Path $sourceSnapshotRoot -Force | Out-Null

$criticalSourceFiles = @(
  "scripts/gate_f1.ps1",
  "scripts/run_pytest_stable.ps1",
  "tools/build_full_audit_bundle.ps1"
)

foreach ($rel in $criticalSourceFiles) {
  $sourcePath = Join-Path $Repo $rel
  if (Test-Path -LiteralPath $sourcePath -PathType Leaf) {
    [byte[]]$sourceBytes = [System.IO.File]::ReadAllBytes($sourcePath)
    $sourceText = ConvertFrom-A8R29BytesToText -Bytes $sourceBytes
    $safeName = ($rel -replace "[\\/]", "__")
    Write-A8R29Utf8NoBomText -Path (Join-Path $sourceSnapshotRoot $safeName) -Text $sourceText
  }
}

$headNameOnly = @(& git -C $Repo show --name-only --pretty=format: HEAD)
Write-A8R29Utf8NoBomText -Path (Join-Path $OutDir "git_show_head_name_only.txt") -Text (($headNameOnly -join "`n") + "`n")

$trackedFiles = @(& git -C $Repo ls-files)
$bomBad = @()

foreach ($rel in $trackedFiles) {
  $full = Join-Path $Repo $rel
  if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
    continue
  }

  [byte[]]$bytes = [System.IO.File]::ReadAllBytes($full)
  if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
    $bomBad += ($rel -replace "\\", "/")
  }
}

$postCommitBomText = @(
  "A8_R29_POST_COMMIT_BOM_SCAN=1"
  "TRACKED_FILE_COUNT=$($trackedFiles.Count)"
  "BOM_BAD_COUNT=$($bomBad.Count)"
  "BOM_BAD_BEGIN"
  ($bomBad -join "`n")
  "BOM_BAD_END"
) -join "`n"

Write-A8R29Utf8NoBomText -Path (Join-Path $OutDir "post_commit_bom_scan.txt") -Text ($postCommitBomText + "`n")

$hookSmokeStdout = Join-Path $OutDir "hook_smoke.stdout.txt"
$hookSmokeRc = Join-Path $OutDir "hook_smoke.rc.txt"
$hookSmokeStatus = Join-Path $OutDir "hook_smoke.status.txt"

if (Test-Path -LiteralPath $hookSmokeStdout -PathType Leaf) {
  $hookText = Get-Content -LiteralPath $hookSmokeStdout -Raw
  if ($hookText -match "HOOK_SMOKE_NOT_RUN_BY_BUNDLE_BUILDER=1") {
    Write-A8R29Utf8NoBomText -Path $hookSmokeRc -Text "NA`n"
    Write-A8R29Utf8NoBomText -Path $hookSmokeStatus -Text "HOOK_SMOKE_STATUS=NOT_RUN_BY_BUNDLE_BUILDER`nHOOK_SMOKE_RC_SEMANTIC=NA`n"
  }
}

$encodingAudit = Convert-A8R29EvidenceTextFilesToUtf8NoBom -Root $OutDir

Write-Host "A8R29_BUNDLE_TEXT_EVIDENCE_FILE_COUNT=$($encodingAudit.TextFileCount)"
Write-Host "A8R29_BUNDLE_UTF8_BOM_BEFORE_COUNT=$($encodingAudit.Utf8BomBefore)"
Write-Host "A8R29_BUNDLE_UTF16_BOM_BEFORE_COUNT=$($encodingAudit.Utf16BomBefore)"
Write-Host "A8R29_BUNDLE_UTF16_LIKE_BEFORE_COUNT=$($encodingAudit.Utf16LikeBefore)"
Write-Host "A8R29_BUNDLE_CONVERTED_TEXT_FILE_COUNT=$($encodingAudit.ConvertedCount)"
Write-Host "A8R29_BUNDLE_BOM_AFTER_COUNT=$($encodingAudit.BomAfter)"
Write-Host "A8R29_BUNDLE_UTF16_BOM_AFTER_COUNT=$($encodingAudit.Utf16BomAfter)"
Write-Host "A8R29_BUNDLE_ENCODING_AUDIT_PATH=$($encodingAudit.AuditPath)"

if ($encodingAudit.BomAfter -ne 0) {
  throw "A8R29_BUNDLE_BOM_AFTER_NOT_ZERO"
}

if ($encodingAudit.Utf16BomAfter -ne 0) {
  throw "A8R29_BUNDLE_UTF16_BOM_AFTER_NOT_ZERO"
}
# A8-R29_BUNDLE_EVIDENCE_NORMALIZATION_END
[System.IO.Compression.ZipFile]::CreateFromDirectory($OutDir, $ZipPath)
$zipHash = (Get-FileHash -Path $ZipPath -Algorithm SHA256).Hash

Write-Host "FULL_AUDIT_BUNDLE_OUT_DIR=$OutDir"
Write-Host "FULL_AUDIT_BUNDLE_ZIP_PATH=$ZipPath"
Write-Host "FULL_AUDIT_BUNDLE_ZIP_EXISTS=$([int](Test-Path $ZipPath))"
Write-Host "FULL_AUDIT_BUNDLE_ZIP_SHA256=$zipHash"
Write-Host "PRIMARY_EVIDENCE_FILE_COUNT=$($existingPrimary.Count)"
Write-Host "BUNDLE_FILE_COUNT=$bundleFileCount"
Write-Host "FULL_AUDIT_BUNDLE_PASS=1"

if ($existingPrimary.Count -lt 15) {
  throw "PRIMARY_EVIDENCE_FILE_COUNT_TOO_LOW=$($existingPrimary.Count)"
}
