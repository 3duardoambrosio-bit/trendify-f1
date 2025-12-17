param(
  [switch]$Fast
)

$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "."

Write-Host "=== PYTEST ==="
if ($Fast) { pytest -q } else { pytest -q }

Write-Host "=== SMOKE P0 ==="
python scripts\run_smoke_p0.py

Write-Host "=== LEDGER TAIL ==="
python -c "from pathlib import Path; p=Path('data/ledger/events.ndjson'); 
lines=p.read_text(encoding='utf-8').splitlines() if p.exists() else [];
tail=lines[-8:]; 
print('ledger_lines=',len(lines)); 
print('tail:'); 
[print(' -',x[:200]) for x in tail]"