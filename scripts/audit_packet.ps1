$ErrorActionPreference="Continue"

function Add-Line($out, $s) { $s | Add-Content -Path $out -Encoding utf8 }
function Run-Cmd($out, $label, $cmd) {
  Add-Line $out "=============================="
  Add-Line $out $label
  Add-Line $out "=============================="
  try {
    $res = Invoke-Expression $cmd 2>&1
    $res | Add-Content -Path $out -Encoding utf8
  } catch {
    Add-Line $out ("ERROR: " + $_.Exception.Message)
  }
  Add-Line $out ""
}

New-Item -ItemType Directory -Force "data\backups\audit" | Out-Null
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$out = "data\backups\audit\audit_$ts.txt"

Add-Line $out ("timestamp=" + (Get-Date -Format o))
Run-Cmd $out "PYTHON" "python -c `"import sys; print(sys.version.replace(chr(10),' '))`""
Run-Cmd $out "GIT STATUS" "git status"
Run-Cmd $out "GIT HEAD" "git rev-parse HEAD"
Run-Cmd $out "GIT BRANCH" "git rev-parse --abbrev-ref HEAD"
Run-Cmd $out "PYTEST" "pytest -q"
Run-Cmd $out "SMOKE P0" "python scripts\run_smoke_p0.py"

if (Test-Path "data\ledger\events.ndjson") {
  Run-Cmd $out "LEDGER TAIL (last 20)" "Get-Content data\ledger\events.ndjson -Tail 20"
}

if (Test-Path "scripts\ledger_stats.py") {
  Run-Cmd $out "LEDGER STATS" "python scripts\ledger_stats.py"
} else {
  Add-Line $out "ledger_stats.py missing (non-fatal)"
}

Write-Host "Audit packet => $out"