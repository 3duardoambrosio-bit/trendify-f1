---
name: f1-snapshot
description: Corre evidence snapshot y verifica gates numéricos (5/5) antes de declarar GREEN.
disable-model-invocation: true
---

# F1 Snapshot (SYNAPSE / TrendifyHub)

## Ejecuta (PowerShell / Windows)
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\evidence_snapshot.ps1

## Verifica (5/5) EN EL ÚLTIMO artifacts\evidence_snapshot_*.txt
Deben existir EXACTAMENTE estas líneas:
- dirty_lines=0
- pytest_exit=0
- doctor_exit=0
- doctor_overall=GREEN
- canonical_rows>=1  (regex: ^canonical_rows=[1-9]\d*$)

Si no da 5/5: STOP y pide el output completo.
