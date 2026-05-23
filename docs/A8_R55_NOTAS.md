# A8-R55 — Notas de cierre condicional

Claude auditó el bundle `synapse_a8_r55_ui_read_model_f878e29_bundle.zip` con veredicto `GO_CLOSE_A8_R55=conditional`.

## Paths de lectura de UI

La UI A8-R55 queda restringida a `runs/operacion_cli_dia1/`.

Paths documentados:

- `RUNS_DIR = Path("runs/operacion_cli_dia1")`
- `PREFERRED_RUN_ROOT = runs/operacion_cli_dia1/operacion_cli_dia1`
- `FALLBACK_RUN_ROOT = runs/operacion_cli_dia1/a8_r54k_gate_false_green_fix/known_cases_runtime`

Nota: `FALLBACK_RUN_ROOT` existe solo como fallback local dentro del mismo prefijo permitido `runs/operacion_cli_dia1/`. No permite lectura genérica de `runs/` ni abre side effects.

## Condición operativa antes de A8-R56

Antes de proponer A8-R56, operar la UI mínimo 3 sesiones y registrar fricción real.
