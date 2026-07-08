Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Read-Secret([string]$Path) {
  if (-not (Test-Path $Path)) {
    return ""
  }

  $raw = Get-Content -Raw -Path $Path -ErrorAction Stop
  if ($null -eq $raw) {
    return ""
  }

  return $raw.Trim()
}

function Get-Sha256Prefix([string]$Value) {
  if ([string]::IsNullOrWhiteSpace($Value)) {
    return "<empty>"
  }

  $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
  $sha = [System.Security.Cryptography.SHA256]::Create()
  try {
    $hashBytes = $sha.ComputeHash($bytes)
    $full = (($hashBytes | ForEach-Object { $_.ToString("x2") }) -join "")
    return $full.Substring(0, 12)
  }
  finally {
    $sha.Dispose()
  }
}

function Write-SecretPresenceReport([string]$Name, [string]$Value) {
  $present = [int](-not [string]::IsNullOrWhiteSpace($Value))
  $hasSpace = [int]($Value -match '\s')
  $length = if ($null -eq $Value) { 0 } else { $Value.Length }
  $sha12 = Get-Sha256Prefix $Value

  Write-Host ("{0}: present={1} len={2} hasSpace={3} sha256_12={4}" -f $Name, $present, $length, $hasSpace, $sha12)
}

$base = Join-Path (Get-Location) "secrets"

$tokPath  = Join-Path $base "meta_access_token.txt"
$aidPath  = Join-Path $base "meta_ad_account_id.txt"
$pagePath = Join-Path $base "meta_page_id.txt"
$igPath   = Join-Path $base "meta_ig_actor_id.txt"

$tok  = Read-Secret $tokPath
$aid  = Read-Secret $aidPath
$page = Read-Secret $pagePath
$ig   = Read-Secret $igPath

# Normaliza ad account: acepta "act_123" o "123" y guarda solo números.
if (-not [string]::IsNullOrWhiteSpace($aid) -and $aid.StartsWith("act_")) {
  $aid = $aid.Replace("act_", "")
}

$env:META_ACCESS_TOKEN  = $tok
$env:META_AD_ACCOUNT_ID = $aid
$env:META_PAGE_ID       = $page
$env:META_IG_ACTOR_ID   = $ig

Write-Host "=== META SECRETS LOADED: SAFE PRESENCE REPORT ONLY ==="
Write-SecretPresenceReport "META_ACCESS_TOKEN"  $tok
Write-SecretPresenceReport "META_AD_ACCOUNT_ID" $aid
Write-SecretPresenceReport "META_PAGE_ID"       $page
Write-SecretPresenceReport "META_IG_ACTOR_ID"   $ig

Write-Host "SYNAPSE_META_LIVE_SET_BY_LOADER=0"
Write-Host "SPEND_REAL_MONEY_SET_BY_LOADER=0"
Write-Host "SECRET_VALUES_PRINTED=0"