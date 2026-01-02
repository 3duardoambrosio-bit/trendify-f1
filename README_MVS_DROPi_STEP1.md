# SYNAPSE — MVS Dropi Step 1 (Product Discovery + Process Layer)
**Filosofía:** ACERO, NO HUMO  
**Objetivo:** Que SYNAPSE jale catálogo de Dropi → haga snapshot auditable → filtre → rankee → emita Top 5 + eventos en ledger.

## Qué incluye (LITE pero serio)
- `scripts/run_product_finder_dropi.py` — runner principal
- `ops/dropi_client.py` — cliente HTTP (headers dual-key)
- `ops/dropi_product_finder.py` — snapshot + normalización + filtros + ranking (fallback si no encuentra tus módulos)
- `ops/ledger_writer.py` — emite eventos en NDJSON con fsync (usa tu core/ledger si existe; si no, fallback)
- `ops/process_guardian.py` + `ops/staircase_map.yaml` — gates + evidencia verificable (files + ledger)

## Variables de entorno
- `DROPI_INTEGRATION_KEY`  (requerida para API)
- `DROPI_BASE_URL` (opcional) default: `https://api.dropi.co/integrations`
- `DROPI_TIMEOUT_S` (opcional) default: 30
- `DROPI_RATE_LIMIT_S` (opcional) default: 0.25  (sleep entre requests)

## Comandos (PowerShell desde el repo)
1) Correr Product Finder (snapshot + Top5 + ledger)
```powershell
$env:PYTHONPATH="."
$env:DROPI_INTEGRATION_KEY="TU_TOKEN_AQUI"
python scripts\run_product_finder_dropi.py --page-size 50 --max-products 5000 --categories "Tecnología,Gadgets,Accesorios,Iluminación"
```

2) Verificar gates (DoD de STEP_1)
```powershell
python scripts\process_guardian.py check --step STEP_1
```

3) Capturar “whisper” (aprendizaje)
```powershell
python scripts\process_guardian.py whisper --step STEP_1 --expectation "..." --reality "..." --learning "..." --obstacle MARKET_REALITY
```

## Dónde guarda
- Snapshot NDJSON: `data/catalog/dropi/YYYYMMDD/catalog_<ts>.ndjson`
- Manifest: `data/catalog/dropi/YYYYMMDD/manifest_<ts>.json`
- Top 5: `evidence/launch_candidates_dropi.json`
- Ledger NDJSON (fallback): `data/ledger/events.ndjson`

## Nota importante
Este paquete NO toca tu Vault/Cashflow/Ledger core. Se conecta por adaptador y cae en fallback seguro si no encuentra tus APIs.
