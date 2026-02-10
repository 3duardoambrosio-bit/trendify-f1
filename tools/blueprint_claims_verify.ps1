Set-StrictMode -Version Latest
$ErrorActionPreference="Stop"

"=== BLUEPRINT CLAIMS VERIFY (STDIN / NO DIRTY) ==="
"BRANCH=$(git branch --show-current)"
"HEAD=$(git log --oneline -1)"

$dirty = (git status --porcelain | Measure-Object).Count
"dirty_lines_pre=$dirty"
if($dirty -ne 0){ throw "PRE_FAIL: dirty_lines_expected_0 got=$dirty" }

$py = @"
from __future__ import annotations
import json, re, sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple
from unittest import mock

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))

HARD = {"http_client_no_network_by_default"}

CLAIMS: Dict[str, List[str]] = {
  "vault_spend_gateway_present": [r"spend_gateway", r"capital_shield", r"\\bvault\\b"],
  "idempotency_present": [r"idempot", r"Idempotency", r"dedup"],
  "ledger_present": [r"\\bledger\\b", r"ndjson", r"append[-_ ]only"],
  "webhook_hmac_sha256_present": [r"\\bHMAC\\b", r"sha256", r"X[-_]Shopify[-_]Hmac[-_]Sha256"],
}

@dataclass
class Check:
  name: str
  ok: bool
  details: Dict[str, Any]

def scan(patterns: List[str]) -> Tuple[int, List[str]]:
  rx = [re.compile(p, re.IGNORECASE) for p in patterns]
  hits: List[str] = []
  count = 0
  for p in ROOT.rglob("*.py"):
    try:
      t = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
      continue
    if any(r.search(t) for r in rx):
      count += 1
      if len(hits) < 15:
        hits.append(str(p.relative_to(ROOT)))
  return count, hits

def check_http_client() -> Check:
  try:
    from synapse.integrations.http_client import SimpleHttpClient
  except Exception as e:
    return Check("http_client_no_network_by_default", False, {"error": repr(e)})

  c = SimpleHttpClient()  # MUST default dry_run=True
  with mock.patch("synapse.integrations.http_client.urllib.request.urlopen") as m:
    r = c.get("https://example.com")
    ok = (r.status == 200) and (r.headers.get("x-dry-run") == "1") and (m.call_count == 0)
    return Check("http_client_no_network_by_default", ok, {
      "status": r.status,
      "x_dry_run": r.headers.get("x-dry-run"),
      "urlopen_call_count": m.call_count,
    })

def main() -> int:
  checks: List[Check] = [check_http_client()]
  for name, pats in CLAIMS.items():
    n, sample = scan(pats)
    checks.append(Check(name, n > 0, {"files_matched": n, "sample": sample}))

  gates_ok = all(c.ok for c in checks if c.name in HARD)
  claims_ok = all(c.ok for c in checks if c.name not in HARD)

  out = {
    "repo_root": str(ROOT),
    "gates_overall": "PASS" if gates_ok else "FAIL",
    "claims_overall": "PASS" if claims_ok else "FAIL",
    "checks": [{"name": c.name, "ok": c.ok, "details": c.details} for c in checks],
  }
  print(json.dumps(out, ensure_ascii=False, indent=2))
  return 0 if gates_ok else 2

if __name__ == "__main__":
  raise SystemExit(main())
"@

"=== RUN PY VIA STDIN ==="
$json = $py | python -
"py_exit=$LASTEXITCODE"
if($LASTEXITCODE -ne 0){ throw "FAIL: blueprint_claims_py_exit=$LASTEXITCODE" }

# Siempre imprime JSON para auditar rápido
$json | Out-Host

$j = $json | ConvertFrom-Json
"gates_overall=$($j.gates_overall)"
"claims_overall=$($j.claims_overall)"
if($j.gates_overall -ne "PASS"){ throw "FAIL: gates_overall_expected_PASS got=$($j.gates_overall)" }

# NUMERIC ACCEPTANCE: http client no-network-by-default
$hc = $j.checks | Where-Object name -eq "http_client_no_network_by_default"
if(-not $hc){ throw "FAIL: missing_check=http_client_no_network_by_default" }
if($hc.ok -ne $true){ throw "FAIL: http_client_check_ok_expected_true" }
if([int]$hc.details.urlopen_call_count -ne 0){ throw "FAIL: urlopen_call_count_expected_0 got=$($hc.details.urlopen_call_count)" }
if($hc.details.x_dry_run -ne "1"){ throw "FAIL: x_dry_run_expected_1 got=$($hc.details.x_dry_run)" }

"OK=1"