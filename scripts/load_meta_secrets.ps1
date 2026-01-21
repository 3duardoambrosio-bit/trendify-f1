Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Read-Secret([string]$path){
  if(-not (Test-Path $path)){ return "" }
  $raw = Get-Content -Raw $path -ErrorAction SilentlyContinue
  if($null -eq $raw){ return "" }
  return $raw.Trim()
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

# Normaliza ad account: acepta "act_123" o "123" y guarda solo números
if($aid.StartsWith("act_")){ $aid = $aid.Replace("act_","") }

$env:META_ACCESS_TOKEN  = $tok
$env:META_AD_ACCOUNT_ID = $aid
$env:META_PAGE_ID       = $page
$env:META_IG_ACTOR_ID   = $ig

# Sanity report (sin leaks)
$prefix = if($tok.Length -ge 4){ $tok.Substring(0,4) } else { $tok }
$hasSpace = [bool]($tok -match '\s')

Write-Host "=== META SECRETS LOADED (SAFE) ==="
Write-Host ("META_ACCESS_TOKEN: len={0} hasSpace={1} prefix={2}" -f $tok.Length, $hasSpace, $prefix)
Write-Host ("META_AD_ACCOUNT_ID: {0}" -f ($(if($aid){$aid}else{"<empty>"})))
Write-Host ("META_PAGE_ID:       {0}" -f ($(if($page){$page}else{"<empty>"})))
Write-Host ("META_IG_ACTOR_ID:   {0}" -f ($(if($ig){$ig}else{"<empty>"})))
