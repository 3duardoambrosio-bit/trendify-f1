# A8-R43G Registry Gates

## Summary

- MODE=LOCAL_ONLY_CODE_HARDENING
- GATE_COUNT=3
- R43D_HIGH_EXPECTED_COUNT=35
- R43E_MEDIUM_EXPECTED_COUNT=90
- R43F_LOW_EXPECTED_COUNT=107
- OPEN_COUNT_EXPECTED=0
- RUNTIME_BEHAVIOR_CHANGED=0
- GATE_MODE=JSON_CONTRACT_ONLY
- SCAN_MARKER_HIT_COUNT=0

## Rule

This central gate validates three risk registry JSON contracts.

It confirms declared count, entry count, and open count.

The individual R43D, R43E, and R43F scripts remain responsible for scan-level drift detection.

## Acceptance

- R43D_HIGH_PASS=1
- R43E_MEDIUM_PASS=1
- R43F_LOW_PASS=1
- A8_R43G_REGISTRY_GATES_PASS=1
