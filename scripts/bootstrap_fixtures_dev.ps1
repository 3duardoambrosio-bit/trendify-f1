Set-StrictMode -Version Latest
$ErrorActionPreference="Stop"
if (-not (Test-Path ".git")) { throw "NO .git (root incorrecto)" }

function Write-LFFile {
  param([Parameter(Mandatory=$true)][string]$Path,[Parameter(Mandatory=$true)][AllowEmptyString()][string]$Content)
  $dir = Split-Path $Path -Parent
  if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  $lf = $Content -replace "`r`n","`n"
  [System.IO.File]::WriteAllText($Path,$lf,[System.Text.UTF8Encoding]::new($false))
}

Write-Host "=== BOOTSTRAP DEV FIXTURES: START ==="
$packPath = "data\evidence\launch_candidates_dropi_dump_f1_v2.json"
$prodDir  = "data\evidence\products"
$prodFile = Join-Path $prodDir "toy-001.json"
$csvPath  = "data\catalog\candidates_real.csv"
$shortlistPath = "data\launch\shortlist_dropi_f1.csv"

New-Item -ItemType Directory -Force -Path (Split-Path $packPath -Parent) | Out-Null
New-Item -ItemType Directory -Force -Path $prodDir | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $csvPath -Parent) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $shortlistPath -Parent) | Out-Null

# Pack contract: isSuccess=true + top.length >= 1
$candidate = [ordered]@{ sku="toy-001"; title="Toy Product 001"; price=9.99; currency="USD"; source="fixture"; supplier="dropi"; url="https://example.invalid/toy-001"; confidence=0.5; score=0.5 }
$pack = [ordered]@{ isSuccess=$true; message="fixture"; top=@($candidate) }
$packJson = ($pack | ConvertTo-Json -Depth 8)

$prod = [ordered]@{ sku="toy-001"; title="Toy Product 001"; notes="fixture"; evidence=@(@{ type="source"; value="dropi" }) }
$prodJson = ($prod | ConvertTo-Json -Depth 8)

$csv = "sku,title,price`n" + "toy-001,Toy Product 001,9.99`n"
$short = "sku`n" + "toy-001`n"

Write-LFFile -Path $packPath -Content ($packJson + "`n")
Write-LFFile -Path $prodFile -Content ($prodJson + "`n")
Write-LFFile -Path $csvPath  -Content $csv
Write-LFFile -Path $shortlistPath -Content $short

"PACK_BYTES={0}"  -f (Get-Item $packPath).Length | Out-Host
"PROD_BYTES={0}"  -f (Get-Item $prodFile).Length | Out-Host
"CSV_BYTES={0}"   -f (Get-Item $csvPath).Length | Out-Host
"SHORT_BYTES={0}" -f (Get-Item $shortlistPath).Length | Out-Host

if ((Get-Item $packPath).Length -lt 200) { throw "FAIL: pack bytes < 200" }
if ((Get-Item $prodFile).Length -lt 50) { throw "FAIL: prod bytes < 50" }
if ((Get-Item $csvPath).Length -lt 10) { throw "FAIL: csv bytes < 10" }
if ((Get-Item $shortlistPath).Length -lt 5) { throw "FAIL: shortlist bytes < 5" }

Write-Host "=== BOOTSTRAP DEV FIXTURES: OK ==="
exit 0
