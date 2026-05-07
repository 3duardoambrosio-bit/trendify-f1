# AGENTS.md  Trendify F1 / SYNAPSE
Regla: ACERO, NO HUMO. Cambios pequeÃ±os, verificables, y con comandos reproducibles.

## Objetivo
Este repo es un sistema operativo para e-commerce (SYNAPSE/Trendify F1).
Los artefactos generados NO se versionan (exports/releases, sha256, etc).

## Comandos de verificaciÃ³n (los 3 sagrados)
- python -m synapse.infra.doctor
- pytest -q
- git status

## PolÃ­ticas de repo
- No versionar outputs generados:
  - exports/releases/**
  - exports/**/*.sha256
  - exports/** (salvo templates explÃ­citos)
- No tocar secretos:
  - Nunca commitear .env, llaves, credenciales.
  - Usar exports/secrets_template.env como plantilla.

## QuÃ© sÃ­ es source of truth
- CÃ³digo: synapse/**
- Config / data determinÃ­stica: data/**
- Tests: tests/**

## QuÃ© es output
- exports/** (artefactos generados)
- data/run, data/ledger, evidence, backups, etc (segÃºn .gitignore)

## EstÃ¡ndar de cambios
- Cada cambio debe dejar el repo pasando doctor + pytest.
- Si se mueven rutas, actualizar docs y scripts asociados.

## Git hooks / Tooling contract

- Hooks source: `.githooks/pre-commit`
- Required local activation: `git config core.hooksPath .githooks`
- Setup command Windows: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/setup_hooks.ps1`
- Setup command Linux/Mac: `bash scripts/setup_hooks.sh`
- Normal commit hook must run `scripts/gate_f1.ps1 hook`
- Full gate before important commits: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/gate_f1.ps1 precommit`
- Hook mode must print `PYTHON_PATH=...`, `PYTHON_VENV_DETECTED=1`, and `HOOK_TEST_TARGETS_FOUND>=5`
- Do not use `--no-verify` unless an audit explicitly authorizes it and the follow-up records why.

## Operational readiness gates

Before any live API activation, real ad spend, real customer-facing launch, or real secrets handling, consult and complete:

- `docs/operational_readiness_checklist.md`
- `docs/go_no_go_template.md`

A GO decision is invalid without explicit human sign-off, numeric capital cap, numeric stop-loss, first SKU selected, kill switch verified, and zero exposed secrets.

## Local control surface

Before public web, Shopify execution, Meta live API, real spend, or secrets, use the local-only control surface contract:

- docs/local_control_surface_contract.md
- scripts/synapse_control_surface.py

The control surface must remain whitelist-only, no-live, no-spend, no-secrets, and Shopify-paused until operational go/no-go gates are completed.

## A8-R28 Tooling and Evidence Hardening

Canonical F1 tooling rules:

- `scripts/gate_f1.ps1` is the canonical local F1 gate.
- `scripts/run_pytest_stable.ps1` is the canonical pytest wrapper.
- `tools/build_full_audit_bundle.ps1` is the canonical full evidence bundle builder.
- Hook and gate pytest execution must use a stable `--basetemp` under `C:/Temp`.
- Do not use repo-relative `Temp*` pytest directories.
- Do not normalize `git commit --no-verify`.
- If a hook is interrupted by `KeyboardInterrupt`, collect manual validation evidence and fix tooling before adding product scope.

Minimum evidence bundle for a code island:

1. `git_head.txt`
2. `git_head_full.txt`
3. `git_last_msg.txt`
4. `git_status.txt`
5. `git_show_head_stat.txt`
6. `git_diff_cached_name_only.txt`
7. `git_diff_cached_check.txt`
8. `control_check.stdout.txt`
9. `control_json.json`
10. `local_health.json`
11. `local_recent_decisions.json`
12. `local_safety_status.json`
13. `targeted_control_surface.stdout.txt`
14. `full_suite.stdout.txt`
15. `hook_smoke.stdout.txt`
16. `summary.txt`

A full evidence bundle must contain at least 15 primary files and must not rely on summary-only claims.
