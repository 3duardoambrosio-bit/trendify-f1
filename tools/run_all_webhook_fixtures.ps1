param(
  [Parameter(Mandatory=$false)][string]$Secret = "shpss_test_secret",
  [Parameter(Mandatory=$false)][string]$FixturesRoot = ".\fixtures\shopify_webhooks",
  [Parameter(Mandatory=$false)][switch]$Quiet
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Die([string]$Msg) { throw $Msg }

function Read-StatusCode([string]$OutDir) {
  $p = Join-Path $OutDir "status_code.txt"
  if(-not (Test-Path $p)) { return -1 }
  $t = (Get-Content $p -Raw).Trim()
  if($t -match '^\d+$'){ return [int]$t }
  return -1
}

function ExpectedExitCodes([int]$ExpectStatus){
  switch($ExpectStatus){
    200 { return @(0) }
    409 { return @(3,0) }  # CLI returns 3 on duplicate; tolerate 0 if normalized
    401 { return @(2,0) }
    400 { return @(1,0) }
    default { return @(0) }
  }
}

$repo = (Resolve-Path ".").Path
$root = Join-Path $repo $FixturesRoot
if(-not (Test-Path $root)) { Die "FAIL: fixtures_root_missing=$root" }

$dirs = Get-ChildItem -Path $root -Directory | Sort-Object Name
$fixture_total = @($dirs).Count
"fixture_total=$fixture_total"
if($fixture_total -lt 1) { Die "FAIL: fixture_total_expected_ge_1 got=$fixture_total" }

$pass = 0
$fail = 0

foreach($d in $dirs){
  $name   = $d.Name
  $fx     = $d.FullName
  $body   = Join-Path $fx "body.bin"
  $hdr    = Join-Path $fx "headers.json"
  $outDir = Join-Path $fx "out"

  # Pre-clean: deterministic "first run = 200"
  if(Test-Path $outDir){ Remove-Item -Recurse -Force $outDir }

  $hasBody = [int](Test-Path $body)
  $hasHdr  = [int](Test-Path $hdr)

  if($hasBody -ne 1 -or $hasHdr -ne 1){
    "fixture=$name status=SKIP missing_body=$hasBody missing_headers=$hasHdr"
    $fail++
    continue
  }

  function Run-One([int]$Expect){
    $cmd = @(
      "powershell","-NoProfile","-ExecutionPolicy","Bypass",
      "-File",".\tools\run_shopify_webhook_fixture.ps1",
      "-FixtureDir",$fx,
      "-Secret",$Secret,
      "-ExpectStatus","$Expect"
    )
    if($Quiet){ $cmd += "-Quiet" }

    $out = & $cmd[0] $cmd[1..($cmd.Count-1)] 2>&1
    $rc = $LASTEXITCODE
    if(-not $Quiet){ $out | Out-Host }

    $status = Read-StatusCode $outDir
    return [pscustomobject]@{ rc=$rc; status=$status; expect=$Expect }
  }

  $r1 = Run-One 200
  $r2 = Run-One 409

  $ok1 = ($r1.status -eq 200) -and ((ExpectedExitCodes 200) -contains $r1.rc)
  $ok2 = ($r2.status -eq 409) -and ((ExpectedExitCodes 409) -contains $r2.rc)

  if($ok1 -and $ok2){
    "fixture=$name status=PASS status200=$($r1.status) rc200=$($r1.rc) status409=$($r2.status) rc409=$($r2.rc)"
    $pass++
  } else {
    "fixture=$name status=FAIL status200=$($r1.status) rc200=$($r1.rc) status409=$($r2.status) rc409=$($r2.rc)"
    $fail++
  }

  # HARD CLEAN: never leave runtime out/
  if(Test-Path $outDir){ Remove-Item -Recurse -Force $outDir }
}

"fixture_pass=$pass"
"fixture_fail=$fail"

if($fail -ne 0){
  "overall=FAIL"
  exit 1
}

"overall=PASS"
exit 0
