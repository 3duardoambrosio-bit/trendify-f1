# A8-R43L — PowerShell Checker Isolation Contract

## Purpose

Harden local PowerShell validation against accidental shell state.

## Contract

No unsafe direct `$LASTEXITCODE` reads in A8 PowerShell checkers/scripts.

## Acceptance

- A8_R43L_PARSE_ERROR_COUNT = 0
- A8_R43L_UNSAFE_LASTEXITCODE_ASSIGNMENT_COUNT = 0
- A8_R43L_UNSAFE_RETURN_LASTEXITCODE_COUNT = 0
- A8_R43L_STRICTMODE_SAFE_MARKER_TOTAL >= 11
- A8_R43L_PASS = 1

## Scope

Local validation only. No ads, assets, suppliers, inventory, publish, or cloud audit.