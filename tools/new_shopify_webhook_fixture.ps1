param(
  [Parameter(Mandatory=$true)][string]$FixtureDir,
  [Parameter(Mandatory=$true)][string]$Secret,
  [string]$BodyText,
  [string]$BodyFile,
  [string]$Topic = "orders/create",
  [string]$ShopDomain = "example.myshopify.com",
  [string]$WebhookId,
  [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference="Stop"

function Write-Utf8NoBom([string]$Path, [string]$Content) {
  $enc = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($Path, $Content, $enc)
}

"=== NEW SHOPIFY WEBHOOK FIXTURE ==="

if(-not $WebhookId){
  $WebhookId = ("wh_" + [Guid]::NewGuid().ToString("N"))
}
"webhook_id=$WebhookId"

if(-not $BodyText -and -not $BodyFile){
  throw "FAIL: provide -BodyText OR -BodyFile"
}
if($BodyText -and $BodyFile){
  throw "FAIL: provide only one of -BodyText or -BodyFile"
}

$fx = (Resolve-Path (Split-Path -Parent $FixtureDir) -ErrorAction SilentlyContinue)
if(-not $fx){
  # parent may not exist; that's fine
}

if(Test-Path $FixtureDir){
  $hasAny = (Get-ChildItem -Force $FixtureDir -ErrorAction SilentlyContinue | Measure-Object).Count
  if($hasAny -gt 0 -and -not $Force){
    throw "FAIL: fixture_dir_not_empty use -Force to overwrite: $FixtureDir"
  }
}
New-Item -Force -ItemType Directory $FixtureDir | Out-Null
$fxPath = (Resolve-Path $FixtureDir).Path
"fixture_dir=$fxPath"

$bodyPath    = Join-Path $fxPath "body.bin"
$headersPath = Join-Path $fxPath "headers.json"

"=== WRITE body.bin ==="
if($BodyFile){
  if(-not (Test-Path $BodyFile)){ throw "FAIL: missing_body_file=$BodyFile" }
  $bytes = [System.IO.File]::ReadAllBytes((Resolve-Path $BodyFile).Path)
  [System.IO.File]::WriteAllBytes($bodyPath, $bytes)
} else {
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($BodyText)
  [System.IO.File]::WriteAllBytes($bodyPath, $bytes)
}

$lenBody = (Get-Item $bodyPath).Length
"body_len=$lenBody"
if($lenBody -lt 1){ throw "FAIL: body_len_expected_ge_1 got=$lenBody" }

"=== COMPUTE HMAC (PY) ==="
# NOTE: compute using repo function for exact parity
$py = @"
from synapse.integrations.shopify_webhook import compute_shopify_hmac_sha256_base64
secret = r'''$Secret'''
body = open(r'''$bodyPath''', 'rb').read()
print(compute_shopify_hmac_sha256_base64(secret, body))
"@
$hmac = ($py | python -).Trim()
if(-not $hmac){ throw "FAIL: hmac_empty" }
"hmac_len=$($hmac.Length)"
if($hmac.Length -ne 44){ throw "FAIL: hmac_len_expected_44 got=$($hmac.Length)" }

"=== WRITE headers.json ==="
$headers = @{
  "X-Shopify-Hmac-Sha256" = $hmac
  "X-Shopify-Webhook-Id"  = $WebhookId
  "X-Shopify-Topic"       = $Topic
  "X-Shopify-Shop-Domain" = $ShopDomain
}
Write-Utf8NoBom -Path $headersPath -Content (ConvertTo-Json $headers -Depth 10)

$lenHeaders = (Get-Item $headersPath).Length
"headers_len=$lenHeaders"
if($lenHeaders -lt 20){ throw "FAIL: headers_len_expected_ge_20 got=$lenHeaders" }

"=== DONE ==="
"OK=1"