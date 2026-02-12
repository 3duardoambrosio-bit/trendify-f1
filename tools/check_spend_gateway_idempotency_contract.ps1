param()

$ErrorActionPreference = "Stop"

Write-Host "=== P0-003 IDEMPOTENCY CONTRACT GATE ==="

# 1) Runtime signature check (la verdad)
$py = @"
import inspect
from ops.spend_gateway_v1 import SpendGateway

sig = inspect.signature(SpendGateway.request)
print("REQUEST_SIG:", sig)

p = sig.parameters.get("idempotency_key")
if p is None:
    raise SystemExit("FAIL: missing_param=idempotency_key")

ann = p.annotation
print("IDEMP_ANNOT:", ann)
print("IDEMP_DEFAULT:", p.default)

if p.default is not inspect._empty:
    raise SystemExit("FAIL: idempotency_key_has_default")

s = str(ann)
if "Optional" in s or "None" in s:
    raise SystemExit(f"FAIL: idempotency_key_is_optional ann={ann}")

print("RESULT: OK_contract_enforced")
"@

$py | python -
if ($LASTEXITCODE -ne 0) { exit 1 }

# 2) Legacy log literal MUST be absent
$legacy = Select-String -Path .\ops\spend_gateway_v1.py -Pattern 'idempotency hit for key=%s' -Quiet
Write-Host ("legacy_idem_log_found=" + $legacy)
if ($legacy) { exit 1 }

Write-Host "P0-003_GATE=PASS"
exit 0
