param(
  [Parameter(Mandatory=$true)][string]$FixtureDir,
  [string]$Secret,
  [string]$SecretFile,
  [string]$OutDir,
  [string]$DedupFile,
  [int]$ExpectStatus = -1,
  [switch]$Quiet
)

Set-StrictMode -Version Latest
$ErrorActionPreference="Stop"

"=== SHOPIFY FIXTURE RUNNER ==="
$fx = (Resolve-Path $FixtureDir).Path
"fixture_dir=$fx"

$headersPath = Join-Path $fx "headers.json"
$bodyPath    = Join-Path $fx "body.bin"

if(-not (Test-Path $headersPath)){ throw "FAIL: missing_headers_json=$headersPath" }
if(-not (Test-Path $bodyPath)){ throw "FAIL: missing_body_bin=$bodyPath" }

if($Secret -and $SecretFile){ throw "FAIL: use -Secret OR -SecretFile, not both" }

if(-not $Secret){
  if(-not $SecretFile){
    # default secret.txt inside fixture (gitignored by repo rule)
    $SecretFile = (Join-Path $fx "secret.txt")
  }
  if(-not (Test-Path $SecretFile)){ throw "FAIL: missing_secret_file=$SecretFile" }
  $Secret = (Get-Content $SecretFile -Raw).Trim()
}

if(-not $Secret){ throw "FAIL: empty_secret" }

if(-not $OutDir){
  $OutDir = (Join-Path $fx "out")
}
New-Item -Force -ItemType Directory $OutDir | Out-Null
"out_dir=$OutDir"

if(-not $DedupFile){
  $DedupFile = (Join-Path $OutDir "dedup.json")
}
"dedup_file=$DedupFile"

$args = @(
  "-m","synapse.integrations.shopify_webhook_cli",
  "--headers",$headersPath,
  "--body",$bodyPath,
  "--secret",$Secret,
  "--dedup-file",$DedupFile,
  "--out-dir",$OutDir
)
if($Quiet){ $args += "--quiet" }

python @args
$cli = $LASTEXITCODE
"cli_exit=$cli"

$statusPath = Join-Path $OutDir "status_code.txt"
if(-not (Test-Path $statusPath)){ throw "FAIL: missing_status_code_txt=$statusPath" }

$sc = (Get-Content $statusPath -Raw).Trim()
"status_code=$sc"

if($ExpectStatus -ge 0){
  if([int]$sc -ne $ExpectStatus){ throw "FAIL: status_code_expected_$ExpectStatus got=$sc" }
}

"OK=1"
exit $cli