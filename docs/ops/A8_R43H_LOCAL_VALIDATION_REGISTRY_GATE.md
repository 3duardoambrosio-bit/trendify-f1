# A8-R43H Local Validation Registry Gate

## Summary

- MODE=LOCAL_ONLY_CODE_HARDENING
- GATE_MODE=LOCAL_VALIDATION_WIRED
- LOCAL_GATE=scripts/gate_f1.ps1
- CENTRAL_GATE=tools/check_a8_r43g_registry_gates.ps1
- PLACEMENT_RULE=BEFORE_ALL_LOCAL_PASS_EXITS
- RUNTIME_BEHAVIOR_CHANGED=0
- SCAN_MARKER_HIT_COUNT=0

## Rule

Local validation invokes the central registry gate before every local PASS exit.

The central registry gate confirms:

- R43D_HIGH_PASS=1
- R43E_MEDIUM_PASS=1
- R43F_LOW_PASS=1
- A8_R43G_REGISTRY_GATES_PASS=1

## Acceptance

- A8_R43H_FUNCTION_BEGIN_COUNT=1
- A8_R43H_FUNCTION_END_COUNT=1
- A8_R43H_LOCAL_PASS_MARKER_COUNT>=1
- A8_R43H_GATE_CALL_COUNT_EQUALS_PASS_COUNT=1
- A8_R43H_GATE_CALL_BEFORE_EACH_LOCAL_PASS=1
- A8_R43H_LOCAL_VALIDATION_REGISTRY_GATE_PASS=1
## StrictMode isolated invocation hardening

A8_R43H_LASTEXITCODE_STRICTMODE_SAFE=1

The checker must not assume `$LASTEXITCODE` is initialized when executed in a clean PowerShell process. If a child checker emits successful output without setting `$LASTEXITCODE`, R43H derives `0` from `$?`; otherwise it uses the explicit native exit code.

Numeric acceptance:

- POST_R43H_CHECKER_RC = 0
- A8_R43H_LOCAL_VALIDATION_REGISTRY_GATE_PASS = 1
- STATUS_COUNT = 0
