<#  OMEGA_ship_batch.ps1
    Cierra un batch Shopify import (SIN curl.exe, SIN HttpClient, SIN PATH):
      - gh.exe hardpath
      - gh auth + setup-git
      - repo assets existe + PUBLIC
      - opcional push assets\generated\<BATCH> -> repo assets
      - baseUrl raw/cdn/auto (sanity HEAD)
      - repatch python (canonical + shopify + gate)
      - limpia unicode invisible en Image Src
      - valida TODAS las Image Src (HTTP 200) con HttpWebRequest HEAD
      - genera IMPORT_KIT + OMEGA_REPORT.json
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)]
  [string]$Batch,

  [string]$Owner = "",
  [string]$AssetsRepo = "trendify-assets",

  [ValidateSet("raw","cdn","auto")]
  [string]$BaseMode = "auto",

  [switch]$DoPushAssets,
  [switch]$Repatch,
  [switch]$RunDoctor,

  [int]$UrlSample = 3,
  [int]$TimeoutMs = 15000
)

$ErrorActionPreference="Stop"

function _ts { (Get-Date).ToString("HH:mm:ss") }
function Ok([string]$m){ Write-Host ("[{0}]  OK   {1}" -f (_ts), $m) -ForegroundColor Green }
function Warn([string]$m){ Write-Host ("[{0}]  WARN {1}" -f (_ts), $m) -ForegroundColor Yellow }
function Info([string]$m){ Write-Host ("[{0}]       {1}" -f (_ts), $m) -ForegroundColor Gray }
function Die([string]$m){ Write-Host ("[{0}]  FAIL {1}" -f (_ts), $m) -ForegroundColor Red; exit 1 }

function Assert-RepoRoot {
  $need = @(
    ".\scripts\patch_canonical_images_from_baseurl.py",
    ".\scripts\patch_shopify_images_from_canonical.py",
    ".\scripts\shopify_contract_gate.py"
  )
  foreach ($p in $need) { if (-not (Test-Path $p)) { Die "No estás en repo root o faltan scripts. Falta: $p" } }
  Ok "repo root OK"
}

function Find-GhExe {
  $c = @(
    "$env:ProgramFiles\GitHub CLI\gh.exe",
    "${env:ProgramFiles(x86)}\GitHub CLI\gh.exe",
    "$env:LOCALAPPDATA\Programs\GitHub CLI\gh.exe"
  ) | Where-Object { $_ -and (Test-Path $_) }
  if ($c) { return ($c | Select-Object -First 1) }
  return $null
}

$script:GhExe = Find-GhExe
if (-not $script:GhExe) { Die "gh.exe no encontrado. Instala GitHub CLI." }

function GH {
  param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Args)
  & $script:GhExe @Args
}

try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

function Ensure-GhAuth {
  GH --version *> $null
  if ($LASTEXITCODE -ne 0) { Die "gh no corre." }

  GH auth status -h github.com *> $null
  if ($LASTEXITCODE -ne 0) {
    Warn "No estás logueado en gh. Abriendo device flow..."
    GH auth login -h github.com -p https -w
    if ($LASTEXITCODE -ne 0) { Die "gh auth login falló." }
  }

  GH auth setup-git *> $null
  if ($LASTEXITCODE -ne 0) { Die "gh auth setup-git falló." }

  Ok "gh auth + setup-git OK"
}

function Get-OwnerIfMissing([string]$OwnerIn){
  if ($OwnerIn -and $OwnerIn.Trim().Length -gt 0) { return $OwnerIn.Trim() }
  $u = (GH api user -q .login 2>$null).Trim()
  if (-not $u) { Die "No pude leer owner con gh api user." }
  return $u
}

function Ensure-AssetsRepoPublic([string]$repoFull,[string]$AssetsRepoName){
  GH api "repos/$repoFull" *> $null
  if ($LASTEXITCODE -ne 0) {
    Warn "Repo assets no existe. Creando: $repoFull (public)"
    GH api -X POST "user/repos" -f "name=$AssetsRepoName" -f "private=false" -f "has_issues=false" -f "has_wiki=false" -f "auto_init=true" *> $null
    if ($LASTEXITCODE -ne 0) { Die "No pude crear repo assets via API." }
  }

  $info = GH api "repos/$repoFull" | ConvertFrom-Json
  if ($null -eq $info) { Die "No pude leer info del repo assets." }

  if ($info.private -eq $true) {
    Warn "Repo assets está private -> public"
    GH api -X PATCH "repos/$repoFull" -f "private=false" *> $null
    if ($LASTEXITCODE -ne 0) { Die "No pude cambiar private=false." }
  }

  $info2 = GH api "repos/$repoFull" | ConvertFrom-Json
  if ($info2.private -eq $true) { Die "Repo sigue privado. Algo bloqueó el cambio." }

  Ok "repo assets public OK"
}

function Clean-Url([string]$s){
  if (-not $s) { return $s }
  $reCf = [regex]'[\p{Cf}]'
  $t = $s
  try { $t = $t.Normalize([System.Text.NormalizationForm]::FormKC) } catch { }
  $t = $t -replace '[<>]',''
  $t = $reCf.Replace($t,'')
  $t = $t.Trim()
  return $t
}

function Join-Url([string]$base,[string]$leaf){
  $b = (Clean-Url $base).TrimEnd('/')
  return "$b/$leaf"
}

function Get-HttpStatus([string]$url,[int]$timeoutMs){
  $u = Clean-Url $url
  if (-not $u) { return 0 }

  $sep = $(if ($u.Contains("?")) { "&" } else { "?" })
  $test = "$u${sep}cb=$(Get-Random)"

  try {
    $req = [System.Net.HttpWebRequest]::Create($test)
    $req.Method = "HEAD"
    $req.AllowAutoRedirect = $true
    $req.UserAgent = "Mozilla/5.0 (OMEGA)"
    $req.Timeout = $timeoutMs
    $req.ReadWriteTimeout = $timeoutMs

    $res = $req.GetResponse()
    $code = [int]$res.StatusCode
    $res.Close()
    return $code
  }
  catch [System.Net.WebException] {
    $we = $_.Exception
    if ($we.Response -ne $null) {
      try {
        $code = [int]$we.Response.StatusCode
        $we.Response.Close()
        return $code
      } catch { }
    }
    return 0
  }
  catch { return 0 }
}

function BaseUrl([string]$repoFull,[string]$Batch,[string]$mode){
  if ($mode -eq "cdn") { return "https://cdn.jsdelivr.net/gh/$repoFull@main/assets/generated/$Batch" }
  return "https://raw.githubusercontent.com/$repoFull/main/assets/generated/$Batch"
}

function Pick-BaseUrlAuto([string]$repoFull,[string]$Batch,[int]$timeoutMs){
  $raw = BaseUrl $repoFull $Batch "raw"
  $cdn = BaseUrl $repoFull $Batch "cdn"

  $rawDemo = Join-Url $raw "demo_00000.png"
  $cdnDemo = Join-Url $cdn "demo_00000.png"

  $c1 = Get-HttpStatus $rawDemo $timeoutMs
  if ($c1 -eq 200) { Ok "baseUrl=raw (200)"; return $raw }

  $c2 = Get-HttpStatus $cdnDemo $timeoutMs
  if ($c2 -eq 200) { Ok "baseUrl=cdn (200)"; return $cdn }

  Die "Sanity falló en RAW($c1) y CDN($c2). Revisa red/DNS/antivirus/proxy."
  return $raw
}

function Push-AssetsBatch([string]$repoFull,[string]$Batch){
  $src = Join-Path (Get-Location) ("assets\generated\" + $Batch)
  if (-not (Test-Path $src)) { Die "No existe: $src" }

  $pngs = Get-ChildItem -Path $src -Filter "*.png" -File -ErrorAction SilentlyContinue
  if (-not $pngs) { Die "No hay PNGs en $src" }
  Ok ("PNGs locales: " + $pngs.Count)

  $tmp = Join-Path $env:TEMP ("trendify-assets-" + $Batch + "-" + (Get-Random))
  Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Path (Join-Path $tmp ("assets\generated\" + $Batch)) -Force | Out-Null
  Copy-Item -Force (Join-Path $src "*.png") (Join-Path $tmp ("assets\generated\" + $Batch)) | Out-Null

  Push-Location $tmp
  git init *> $null
  git config user.name  "trendify-assets-bot" *> $null
  git config user.email "trendify-assets-bot@users.noreply.github.com" *> $null
  git add . *> $null
  git commit -m ("assets batch " + $Batch) *> $null
  git branch -M main *> $null

  $remoteUrl = "https://github.com/$repoFull.git"
  $remotes = git remote
  if ($remotes -contains "origin") { git remote set-url origin $remoteUrl *> $null } else { git remote add origin $remoteUrl *> $null }

  git push -u origin main --force
  if ($LASTEXITCODE -ne 0) { Pop-Location; Die "git push falló (assets repo)." }
  Pop-Location

  Ok "Assets push OK"
}

function Repatch-Csvs([string]$Batch,[string]$baseUrl){
  $canonIn  = "exports\releases\_batch\$Batch\canonical_products.csv"
  $canonOut = "exports\releases\_batch\$Batch\canonical_products.patched.csv"
  $shopIn   = "exports\releases\_batch\$Batch\shopify_import_all.csv"
  $shopOut  = "exports\releases\_batch\$Batch\shopify_import_all.patched.csv"
  $imgDir   = "assets\generated\$Batch"

  if (-not (Test-Path $canonIn)) { Die "No existe: $canonIn" }
  if (-not (Test-Path $shopIn))  { Die "No existe: $shopIn" }
  if (-not (Test-Path $imgDir))  { Die "No existe: $imgDir" }

  Info "patch canonical..."
  & python .\scripts\patch_canonical_images_from_baseurl.py `
    --canonical $canonIn `
    --out $canonOut `
    --images-dir $imgDir `
    --base-url $baseUrl `
    --force 2>&1 | Out-Host
  if ($LASTEXITCODE -ne 0) { Die "patch_canonical_images_from_baseurl falló." }
  Ok "canonical patched OK"

  Info "patch shopify..."
  & python .\scripts\patch_shopify_images_from_canonical.py `
    --shopify-csv $shopIn `
    --canonical-csv $canonOut `
    --out $shopOut 2>&1 | Out-Host
  if ($LASTEXITCODE -ne 0) { Die "patch_shopify_images_from_canonical falló." }
  Ok "shopify patched OK"

  Info "contract gate..."
  & python .\scripts\shopify_contract_gate.py $shopOut --mode prod 2>&1 | Out-Host
  if ($LASTEXITCODE -ne 0) { Die "shopify_contract_gate falló." }
  Ok "contract gate OK"

  return $shopOut
}

function Clean-Csv([string]$inCsv,[string]$outCsv){
  if (-not (Test-Path $inCsv)) { Die "No existe: $inCsv" }

  $reCf = [regex]'[\p{Cf}]'
  Import-Csv $inCsv | ForEach-Object {
    if ($_.'Image Src') {
      $s = $_.'Image Src'
      try { $s = $s.Normalize([System.Text.NormalizationForm]::FormKC) } catch { }
      $s = $s -replace '[<>]',''
      $s = $reCf.Replace($s,'')
      $s = $s.Trim()
      $_.'Image Src' = $s
    }
    $_
  } | Export-Csv $outCsv -NoTypeInformation -Encoding UTF8

  Ok "CSV limpio OK"
}

function Validate-UrlsFromCsv([string]$csvPath,[int]$timeoutMs,[string]$badOut){
  if (-not (Test-Path $csvPath)) { Die "CSV no existe: $csvPath" }

  $urls = Import-Csv $csvPath |
    Where-Object { $_.'Image Src' } |
    Select-Object -ExpandProperty 'Image Src' -Unique |
    ForEach-Object { Clean-Url $_ }

  if (-not $urls) { Die "No encontré Image Src en $csvPath" }

  $bad = New-Object System.Collections.Generic.List[string]
  foreach ($u in $urls) {
    $code = Get-HttpStatus $u $timeoutMs
    if ($code -ne 200) { $bad.Add(("{0} {1}" -f $code, $u)) }
  }

  if ($bad.Count -gt 0) {
    $bad | Set-Content -Encoding UTF8 $badOut
    Die "URLs malas detectadas: $($bad.Count). Ver: $badOut"
  }

  Ok "URLs 200 OK (todas)"
}

function Make-ImportKit([string]$Batch,[string]$finalCsv,[string]$baseUrl,[string]$repoFull){
  $kit = "exports\releases\_batch\$Batch\IMPORT_KIT"
  New-Item -ItemType Directory -Force $kit | Out-Null
  Copy-Item -Force $finalCsv (Join-Path $kit "shopify_import_all.FINAL.csv")

  $report = @{
    batch = $Batch
    repo_assets = $repoFull
    base_url = $baseUrl
    final_csv = $finalCsv
    kit_dir = $kit
    generated_at = (Get-Date).ToString("s")
  } | ConvertTo-Json -Depth 6

  $reportPath = "exports\releases\_batch\$Batch\OMEGA_REPORT.json"
  $report | Set-Content -Encoding UTF8 $reportPath

  @"
IMPORT KIT (Trendify F1)
Batch: $Batch
Repo assets: $repoFull
BaseUrl: $baseUrl
Archivo: shopify_import_all.FINAL.csv
Shopify: Admin -> Products -> Import
"@ | Set-Content -Encoding UTF8 (Join-Path $kit "README.txt")

  Ok "IMPORT_KIT OK"
  Ok "REPORT OK"
}

function Run-Doctor([string]$Batch){
  & python .\scripts\release_batch_doctor.py --batch-dir "exports\releases\_batch\$Batch" --mode prod 2>&1 | Out-Host
  if ($LASTEXITCODE -ne 0) { Die "release_batch_doctor falló." }
  Ok "doctor OK"
}

# ========================= RUN =========================
Assert-RepoRoot
Ensure-GhAuth

$Owner = Get-OwnerIfMissing $Owner
$repoFull = "$Owner/$AssetsRepo"
Ok "owner=$Owner"
Ok "assetsRepo=$repoFull"

Ensure-AssetsRepoPublic $repoFull $AssetsRepo

if ($DoPushAssets) { Push-AssetsBatch $repoFull $Batch }

if ($BaseMode -eq "auto") { $baseUrl = Pick-BaseUrlAuto $repoFull $Batch $TimeoutMs }
else { $baseUrl = BaseUrl $repoFull $Batch $BaseMode }

$demo = Join-Url $baseUrl "demo_00000.png"
$cSan = Get-HttpStatus $demo $TimeoutMs
if ($cSan -ne 200) { Die "sanity falló (demo_00000.png) HTTP=$cSan baseUrl=$baseUrl" }
Ok "sanity OK"

$shopPatched = "exports\releases\_batch\$Batch\shopify_import_all.patched.csv"
if ($Repatch) { $shopPatched = Repatch-Csvs $Batch $baseUrl }
else { if (-not (Test-Path $shopPatched)) { Die "No existe $shopPatched (usa -Repatch)" } }

$finalCsv = "exports\releases\_batch\$Batch\shopify_import_all.FINAL.csv"
Clean-Csv $shopPatched $finalCsv

$badOut = "exports\releases\_batch\$Batch\bad_urls.txt"
Validate-UrlsFromCsv $finalCsv $TimeoutMs $badOut

Make-ImportKit $Batch $finalCsv $baseUrl $repoFull

if ($RunDoctor) { Run-Doctor $Batch }

Import-Csv $finalCsv |
  Where-Object { $_.'Image Src' } |
  Select-Object -ExpandProperty 'Image Src' -Unique |
  Select-Object -First $UrlSample |
  ForEach-Object { Clean-Url $_ } |
  ForEach-Object { Write-Host $_ }

Ok "DONE"
Ok "FINAL CSV: exports\releases\_batch\$Batch\shopify_import_all.FINAL.csv"
Ok "IMPORT KIT: exports\releases\_batch\$Batch\IMPORT_KIT"
