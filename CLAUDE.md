# SYNAPSE / TrendifyHub — Claude Code Operating Manual (F1 / ACERO, NO HUMO)

## 0) Regla madre
- NO improvises. NO dejes el repo sucio. NO declares “done” sin evidencia numérica.

## 1) Gates obligatorios (numéricos)
Antes de commit/PR/merge, ejecuta:

- Snapshot:
  powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\evidence_snapshot.ps1

Y valida en el ÚLTIMO `artifacts\evidence_snapshot_*.txt` que existan EXACTAMENTE estas líneas:
- dirty_lines=0
- pytest_exit=0
- doctor_exit=0
- doctor_overall=GREEN
- canonical_rows>=1 (regex: ^canonical_rows=[1-9]\d*$)

Si falta cualquiera: STOP y pide output completo.

## 2) Workflow estándar
1) Crea branch
2) Implementa cambios
3) Corre snapshot y valida (5/5)
4) Commit con mensaje claro
5) Push + PR
6) Espera checks en verde
7) Merge (squash) + borrar branch
8) Sync local main + snapshot final

## 3) Comandos canónicos (Windows / PowerShell)
- Snapshot:
  powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\evidence_snapshot.ps1

- Repo limpio:
  git status --porcelain | Measure-Object

## 4) Estilo de trabajo
- Cambios pequeños pero completos.
- Siempre deja evidencia (snapshot) en artifacts (ignorados por git).
- No “rollback por si acaso”: solo si algo falla y con output pegado.
