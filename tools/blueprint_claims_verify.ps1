param([switch]$AllowDirty)
Set-StrictMode -Version Latest
$ErrorActionPreference="Stop"

"=== BLUEPRINT CLAIMS VERIFY (STDIN) ==="
"BRANCH=$(git branch --show-current)"
"HEAD=$(git log --oneline -1)"

$dirty = (git status --porcelain | Measure-Object).Count
"dirty_lines_pre=$dirty"
if((-not $AllowDirty) -and ($dirty -ne 0)){
  throw "PRE_FAIL: dirty_lines_expected_0 got=$dirty (hint: re-run with -AllowDirty during implementation)"
}

$py = @"
from __future__ import annotations
import json, re, sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple
from unittest import mock

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))

HARD = {"http_client_no_network_by_default","shopify_webhook_hmac_and_dedup"}

@dataclass
class Check:
  name: str
  ok: bool
  details: Dict[str, Any]

def check_http_client() -> Check:
  try:
    from synapse.integrations.http_client import SimpleHttpClient
  except Exception as e:
    return Check("http_client_no_network_by_default", False, {"error": repr(e)})
  c = SimpleHttpClient()
  with mock.patch("synapse.integrations.http_client.urllib.request.urlopen") as m:
    r = c.get("https://example.com")
    ok = (r.status == 200) and (r.headers.get("x-dry-run") == "1") and (m.call_count == 0)
    return Check("http_client_no_network_by_default", ok, {"status": r.status,"x_dry_run": r.headers.get("x-dry-run"),"urlopen_call_count": m.call_count})

def check_shopify_webhook() -> Check:
  try:
    from synapse.integrations.shopify_webhook import compute_shopify_hmac_sha256_base64, process_shopify_webhook
  except Exception as e:
    return Check("shopify_webhook_hmac_and_dedup", False, {"error": repr(e)})
  secret = "shpss_test_secret"
  body = b'{"hello":"world","n":1}'
  h = compute_shopify_hmac_sha256_base64(secret, body)
  headers = {"X-Shopify-Hmac-Sha256": h, "X-Shopify-Webhook-Id": "wh_1"}
  d = set()
  r1 = process_shopify_webhook(secret=secret, headers=headers, body=body, dedup_set=d)
  r2 = process_shopify_webhook(secret=secret, headers=headers, body=body, dedup_set=d)
  ok = (r1.accepted is True and r1.status_code == 200 and r2.accepted is False and r2.status_code == 409 and len(d) == 1)
  return Check("shopify_webhook_hmac_and_dedup", ok, {"r1_status": r1.status_code,"r2_status": r2.status_code,"dedup_size": len(d)})

def main() -> int:
  checks = [check_http_client(), check_shopify_webhook()]
  gates_ok = all(c.ok for c in checks if c.name in HARD)
  out = {"repo_root": str(ROOT),"gates_overall": "PASS" if gates_ok else "FAIL","checks": [{"name": c.name, "ok": c.ok, "details": c.details} for c in checks]}
  print(json.dumps(out, ensure_ascii=False, indent=2))
  return 0 if gates_ok else 2

if __name__ == "__main__":
  raise SystemExit(main())
"@

"=== RUN PY VIA STDIN ==="
$json = $py | python -
$code = $LASTEXITCODE
"py_exit=$code"
$json | Out-Host
if($code -ne 0){ throw "FAIL: blueprint_claims_py_exit=$code" }

$okLines = ($json | Select-String '"gates_overall": "PASS"' | Measure-Object).Count
"gates_pass_lines=$okLines"
if($okLines -ne 1){ throw "FAIL: gates_pass_lines_expected_1 got=$okLines" }

"OK=1"