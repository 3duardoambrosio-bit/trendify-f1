# A8-R43K — Local Pass Contract

## Purpose

A8-R43K hardens local validation by making successful local PASS exits auditable.

R43I proved that a critical gate can exist and still be bypassed when not all successful local-validation exits execute it. R43K converts that failure mode into a contract.

## Contract

scripts/gate_f1.ps1 must not expose a non-help successful exit 0 path before the critical registry gate invocation.

## Checker

Tool:

- tools/check_a8_r43k_local_pass_contract.ps1

The checker validates:

- scripts/gate_f1.ps1 exists.
- exit 0 appears at least once.
- at least one non-help local PASS exit 0 exists.
- tools/check_a8_r43g_registry_gates.ps1 appears before every non-help local PASS exit 0.
- --no-verify does not appear inside scripts/gate_f1.ps1.
- literal tools/*.ps1 references inside scripts/gate_f1.ps1 point to existing files.

## Numeric acceptance criteria

Required:

- A8_R43K_EXIT_ZERO_COUNT >= 1
- A8_R43K_LOCAL_PASS_EXIT_ZERO_COUNT >= 1
- A8_R43K_REGISTRY_GATE_HIT_COUNT >= 1
- A8_R43K_EXIT_ZERO_BEFORE_REGISTRY_GATE_COUNT = 0
- A8_R43K_NO_VERIFY_IN_GATE_COUNT = 0
- A8_R43K_MISSING_TOOL_REFERENCE_COUNT = 0
- A8_R43K_PASS = 1

## Scope

This front does not reopen R43G, R43H, R43I, or R43J. It prevents future local PASS bypass drift.
