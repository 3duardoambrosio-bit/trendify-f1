# SYNAPSE / TrendifyHub  Claude Code Operating Manual (F1 / ACERO, NO HUMO)

## 0) Regla madre
- NO improvises. NO dejes el repo sucio. NO declares done sin evidencia numérica.

## 1) Gates obligatorios (numéricos)
Antes de declarar GREEN / cerrar PR / merge, el repo DEBE estar limpio:
- git status --porcelain  => 0 líneas

Luego corre snapshot:
- powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\evidence_snapshot.ps1

Y valida en el ÚLTIMO `artifacts\evidence_snapshot_*.txt` que existan EXACTAMENTE estas líneas:
- dirty_lines=0
- pytest_exit=0
- doctor_exit=0
- doctor_overall=GREEN
- canonical_rows>=1 (regex: ^canonical_rows=[1-9]\d*$)

Si falta cualquiera: STOP y pide output completo.

## 2) Skill de proyecto (slash command)
Este repo define `/f1-snapshot` en:
- .claude/skills/f1-snapshot/SKILL.md

Úsalo cuando quieras forzar el protocolo F1.

## 3) Workflow estándar
1) Crea branch
2) Implementa cambios
3) Commit (precommit gate debe pasar)
4) Repo limpio (0 líneas)
5) Snapshot + asserts 5/5
6) Push + PR
7) Checks en verde
8) Merge (squash) + borrar branch
9) Sync local main + snapshot final (5/5)

## 4) Estilo de trabajo
- Cambios pequeños pero completos.
- Evidencia en artifacts/ (ignorados por git).
- No rollback por si acaso: solo si algo falla y con output pegado.
