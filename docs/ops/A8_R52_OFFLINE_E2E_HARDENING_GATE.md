# A8-R52 OFFLINE E2E HARDENING GATE

## Purpose

A8-R52 converts the proven offline burn-in E2E run into an official, repeatable, auditable local gate.

This gate proves that SYNAPSE can run as an assembled offline system without Shopify writes, Meta live mutation, Dropi automation, spend, launch, or external mutation.

## Canonical command

powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/run_offline_e2e_gate.ps1 -Cycles 25

## Expected hard gates

| Gate | Expected |
|---|---:|
| cycles | 25 |
| dispatch_count | 100 |
| ledger_event_count | 75 |
| BLOCKED | 25 |
| DISPATCHED | 25 |
| SKIPPED | 50 |
| pre_spend_gate_blocked | 25 |
| CLI dirty_lines | 0 |
| CLI doctor_overall | GREEN |
| flag_shopify_live | 0 |
| flag_meta_live_api | 0 |
| flag_dropi_live_orders | 0 |
| repo status after gate | 0 |

## Evidence

The gate writes evidence under C:\Temp\SYNAPSE_A8_R52_OFFLINE_E2E_GATE_<timestamp> by default.

Expected evidence:

- evidence/burnin_summary.json
- evidence/ledger.ndjson
- evidence/idem.sqlite3
- logs/synapse_cli_status.txt
- logs/synapse_cli_doctor.txt
- A8_R52_OFFLINE_E2E_GATE_MANIFEST.txt
- synapse_a8_r52_offline_e2e_gate_evidence.zip

## Safety posture

- NO_LAUNCH=1
- NO_SPEND=1
- NO_EXTERNAL_MUTATION=1
- NO_SHOPIFY_MUTATION=1
- NO_META_MUTATION=1
- NO_DROPI_MUTATION=1

## Meaning of PASS

A8_R52_OFFLINE_E2E_GATE_PASS=1 means the offline burn-in E2E executed, expected numeric outcomes matched, ledger and idempotency artifacts exist, CLI status is clean, doctor is GREEN, evidence was packaged, and the repo remained clean.
