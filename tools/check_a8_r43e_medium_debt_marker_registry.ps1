param(
  [string]$Repo = "C:\Users\edu_a\OneDrive\Documentos\trendify-fase1"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Read-Utf8Safe($Path) {
  if (-not (Test-Path $Path)) { return "" }
  $bytes = [System.IO.File]::ReadAllBytes($Path)
  if ($bytes.Length -eq 0) { return "" }
  $utf8 = New-Object System.Text.UTF8Encoding($false, $false)
  return $utf8.GetString($bytes)
}

function Get-Sha256Text($Text) {
  $utf8 = New-Object System.Text.UTF8Encoding($false)
  $bytes = $utf8.GetBytes($Text)
  $sha = [System.Security.Cryptography.SHA256]::Create()
  try {
    return ([BitConverter]::ToString($sha.ComputeHash($bytes)) -replace "-", "").ToUpperInvariant()
  }
  finally {
    $sha.Dispose()
  }
}

function Classify-DebtMarker($Path, $Marker, $Snippet) {
  $p = ($Path -replace "\\", "/")
  $lower = $Snippet.ToLowerInvariant()

  if ($p.StartsWith("docs/")) { return [pscustomobject]@{ Risk = "LOW" } }
  if ($p.StartsWith("tests/")) { return [pscustomobject]@{ Risk = "LOW" } }

  if ($p.StartsWith("scripts/") -or $p.StartsWith("tools/")) {
    if ($lower -match "bypass|skip|unsafe|disable|temporary|workaround|hack") {
      return [pscustomobject]@{ Risk = "MEDIUM" }
    }
    return [pscustomobject]@{ Risk = "LOW" }
  }

  if ($p.StartsWith("src/") -or $p.StartsWith("synapse/")) {
    if ($Marker -in @("FIXME", "HACK", "XXX")) {
      return [pscustomobject]@{ Risk = "HIGH" }
    }

    if ($lower -match "temporary|workaround|deprecated|legacy") {
      return [pscustomobject]@{ Risk = "HIGH" }
    }

    return [pscustomobject]@{ Risk = "MEDIUM" }
  }

  if ($lower -match "bypass|unsafe|skip|disable") {
    return [pscustomobject]@{ Risk = "HIGH" }
  }

  return [pscustomobject]@{ Risk = "MEDIUM" }
}

function Get-CurrentMediumRiskFindings($RepoRoot) {
  $tmp = Join-Path $env:TEMP ("a8_r43e_medium_scan_" + [guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Path $tmp -Force | Out-Null

  $rawOut = Join-Path $tmp "grep.out.txt"
  $rawErr = Join-Path $tmp "grep.err.txt"
  $pattern = "(TODO|FIXME|HACK|XXX|TBD|WORKAROUND|TEMPORARY|LEGACY|DEPRECATED|TECH_DEBT|DEBT)"
  $cmd = 'git.exe grep -n -I -i -E "' + $pattern + '" -- . 1>"' + $rawOut + '" 2>"' + $rawErr + '"'

  & cmd.exe /d /c ('cd /d "' + $RepoRoot + '" && ' + $cmd)
  $a8r43lLastCommandSucceeded = $?
  $a8r43lLastExitCodeVar = Get-Variable -Name LASTEXITCODE -ErrorAction SilentlyContinue
  if ($null -eq $a8r43lLastExitCodeVar -or $null -eq $a8r43lLastExitCodeVar.Value) {
      if ($a8r43lLastCommandSucceeded) {
          $rc = 0
      }
      else {
          $rc = 1
      }
  }
  else {
      $rc = [int]$a8r43lLastExitCodeVar.Value
  }
  # A8_R43L_LASTEXITCODE_STRICTMODE_SAFE=1
  if ($null -eq $rc) { $rc = 0 }

  if ($rc -ne 0 -and $rc -ne 1) {
    throw "GIT_GREP_FAILED rc=$rc"
  }

  $rawText = Read-Utf8Safe $rawOut
  $rawLines = @($rawText -split "`r?`n" | Where-Object { $_ -and $_.Trim().Length -gt 0 })

  $excludedPrefixes = @(
    ".git/",
    ".pytest_cache/",
    "__pycache__/",
    "venv/",
    ".venv/",
    "node_modules/",
    "dist/",
    "build/",
    ".mypy_cache/",
    ".ruff_cache/"
  )

  $excludedExactPaths = @(
    "docs/ops/a8_r43e_medium_risk_debt_marker_registry.json",
    "docs/ops/A8_R43E_MEDIUM_RISK_DEBT_MARKER_REGISTRY.md",
    "tools/check_a8_r43e_medium_debt_marker_registry.ps1",
    "docs/ops/a8_r43f_low_risk_debt_marker_registry.json",
    "docs/ops/A8_R43F_LOW_RISK_DEBT_MARKER_REGISTRY.md",
    "tools/check_a8_r43f_low_debt_marker_registry.ps1"
  )

  $markerRegex = [regex]"(?i)\b(TODO|FIXME|HACK|XXX|TBD|WORKAROUND|TEMPORARY|LEGACY|DEPRECATED|TECH_DEBT|DEBT)\b"
  $seen = New-Object "System.Collections.Generic.HashSet[string]"
  $findings = New-Object System.Collections.Generic.List[object]

  foreach ($line in $rawLines) {
    $match = [regex]::Match($line, "^(?<path>.*?):(?<line>\d+):(?<snippet>.*)$")
    if (-not $match.Success) { continue }

    $path = ($match.Groups["path"].Value -replace "\\", "/")
    $lineNo = [int]$match.Groups["line"].Value
    $snippet = $match.Groups["snippet"].Value.Trim()

    if ($excludedExactPaths -contains $path) {
      continue
    }

    $excluded = $false
    foreach ($prefix in $excludedPrefixes) {
      if ($path.StartsWith($prefix)) {
        $excluded = $true
        break
      }
    }
    if ($excluded) { continue }

    $markerMatches = @($markerRegex.Matches($snippet))
    if ($markerMatches.Count -eq 0) { continue }

    $markers = @($markerMatches | ForEach-Object { $_.Groups[1].Value.ToUpperInvariant() } | Sort-Object -Unique)

    foreach ($marker in $markers) {
      $classification = Classify-DebtMarker -Path $path -Marker $marker -Snippet $snippet
      if ($classification.Risk -ne "MEDIUM") { continue }

      $keySource = "$path`n$lineNo`n$marker`n$snippet"
      $snippetSha = Get-Sha256Text $keySource
      $key = "$path::$lineNo::$marker::$snippetSha"

      if ($seen.Contains($key)) { continue }
      [void]$seen.Add($key)

      $findings.Add([pscustomobject]@{
        key = $key
        path = $path
        line = $lineNo
        marker = $marker
        snippet_sha256 = $snippetSha
        snippet = $snippet
      }) | Out-Null
    }
  }

  return @($findings | Sort-Object path,line,marker)
}

Set-Location $Repo

$registryPath = Join-Path $Repo "docs/ops/a8_r43e_medium_risk_debt_marker_registry.json"
if (-not (Test-Path $registryPath)) {
  throw "REGISTRY_NOT_FOUND=$registryPath"
}

$registry = Get-Content -Raw -Path $registryPath | ConvertFrom-Json
$currentMedium = @(Get-CurrentMediumRiskFindings -RepoRoot $Repo)

$currentKeys = New-Object "System.Collections.Generic.HashSet[string]"
foreach ($item in $currentMedium) {
  [void]$currentKeys.Add([string]$item.key)
}

$registeredKeys = New-Object "System.Collections.Generic.HashSet[string]"
foreach ($entry in $registry.entries) {
  [void]$registeredKeys.Add([string]$entry.key)
}

$unmanaged = @($currentMedium | Where-Object { -not $registeredKeys.Contains([string]$_.key) })
$stale = @($registry.entries | Where-Object { -not $currentKeys.Contains([string]$_.key) })

Write-Host "CURRENT_MEDIUM_RISK_COUNT=$($currentMedium.Count)"
Write-Host "REGISTERED_MEDIUM_RISK_COUNT=$($registry.entries.Count)"
Write-Host "UNMANAGED_MEDIUM_RISK_COUNT=$($unmanaged.Count)"
Write-Host "STALE_REGISTERED_MEDIUM_RISK_COUNT=$($stale.Count)"
Write-Host "SELF_SURFACE_EXCLUSION_ACTIVE=1"

if ($currentMedium.Count -ne $registry.entries.Count) {
  throw "CURRENT_MEDIUM_RISK_COUNT_MISMATCH current=$($currentMedium.Count) registered=$($registry.entries.Count)"
}

if ($unmanaged.Count -ne 0) {
  Write-Host "UNMANAGED_BEGIN"
  $unmanaged | ForEach-Object { Write-Host "$($_.path):$($_.line):$($_.marker):$($_.snippet)" }
  Write-Host "UNMANAGED_END"
  throw "UNMANAGED_MEDIUM_RISK_DEBT_MARKERS"
}

if ($stale.Count -ne 0) {
  Write-Host "STALE_BEGIN"
  $stale | ForEach-Object { Write-Host "$($_.path):$($_.line):$($_.marker):$($_.snippet)" }
  Write-Host "STALE_END"
  throw "STALE_MEDIUM_RISK_DEBT_REGISTRY"
}

Write-Host "A8_R43E_MEDIUM_RISK_DEBT_REGISTRY_PASS=1"