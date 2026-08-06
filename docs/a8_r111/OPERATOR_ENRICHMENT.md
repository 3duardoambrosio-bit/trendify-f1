# A8-R111 â€” Operator Enrichment & Full Pack Unlock

## PropÃ³sito

Este flujo convierte un candidato importado por R110 en un candidato con
contexto explÃ­cito del operador. Todo ocurre de forma local. No usa red, no
publica en Shopify o Meta, no gasta dinero y conserva
`decision.permission_gate=REVIEW`.

El sistema no investiga ni inventa el brief. El operador llena Ãºnicamente
datos que conoce. El motor metodolÃ³gico sellado decide si el contexto puede
usarse, debe quedar bloqueado o necesita mÃ¡s informaciÃ³n.

## Flujo de menos de 10 minutos

### 1. Construir el workspace base

```powershell
python -m synapse.ui.operator_enrichment_cli rebuild `
  --csv .\ruta\catalogo.csv `
  --workspace .\artifacts\operator_workspace
```

Consulta los candidatos generados:

```powershell
Get-ChildItem .\artifacts\operator_workspace\candidates\*.json
```

### 2. Crear la plantilla

Sustituye `<fixture_id>` por el nombre del candidato sin `.json`:

```powershell
python -m synapse.ui.operator_enrichment_cli template `
  --workspace .\artifacts\operator_workspace `
  --fixture-id <fixture_id>
```

La plantilla queda en:

```text
artifacts/operator_workspace/candidates_input/<fixture_id>.enrichment.json
```

El comando no reemplaza un archivo existente. Esto evita borrar el trabajo del
operador.

### 3. Llenar Ãºnicamente informaciÃ³n real

Campos metodolÃ³gicos:

- `product_facts`: hechos verificables del producto.
- `buyer_state`: estado real del comprador.
- `proof_available`: prueba disponible hoy; puede quedar vacÃ­a.
- `claim_risk_hints`: `low`, `high`, `medical`, `safety` o `unclear`.
- `channel`: `Meta` por defecto.
- `margin_profile`: `tight`, `acceptable` o `healthy`.

Campos que alimentan la riqueza R109:

- `buyer_pain`
- `target_audience`
- `objections`
- `proof_available`
- `desires`
- `differentiators`
- `market_context`
- `customer_language`

Ocho campos completos producen `INPUT_RICH`. Cuatro a siete producen
`INPUT_PARTIAL`. Menos de cuatro producen `INPUT_LOW`.

No copies URL, tokens, credenciales ni texto que no puedas sostener con
evidencia.

### 4. Reconstruir

```powershell
python -m synapse.ui.operator_enrichment_cli rebuild `
  --csv .\ruta\catalogo.csv `
  --workspace .\artifacts\operator_workspace
```

Abre:

```powershell
Start-Process .\artifacts\operator_workspace\workspace.html
```

## Estados

| Estado | Significado |
|---|---|
| `ABSENT` | No existe enrichment; el candidato continÃºa bloqueado honestamente. |
| `PARTIAL` | Hay informaciÃ³n Ãºtil, pero falta riqueza o contexto metodolÃ³gico. |
| `INVALID_INPUT` | JSON invÃ¡lido, tipos incorrectos, fixture incorrecto o token prohibido. |
| `ACCEPTED` | Motor aceptÃ³ el contexto e `INPUT_RICH` desbloqueÃ³ packs locales. |
| `BLOCKED` | El motor emitiÃ³ razÃ³n y acciÃ³n; no se habilita copy comercial. |
| `FALLBACK` | El motor no encontrÃ³ una ruta experta segura; los packs siguen cerrados. |

## QuÃ© se genera

- `intake_report.json`
- `candidates/<fixture_id>.json`
- `workspace.html`

Los archivos de entrada del operador permanecen separados en
`candidates_input/` y nunca se borran durante `rebuild`.

## LÃ­mites

- Sin descubrimiento automÃ¡tico de nichos.
- Sin auto-enriquecimiento web.
- Sin Shopify, Dropi o Meta live.
- Sin gasto.
- Sin publicaciÃ³n.
- Sin modificaciÃ³n del motor metodolÃ³gico sellado.
- Todo copy habilitado deriva del `safe_output` del motor y de campos explÃ­citos
  del operador.
