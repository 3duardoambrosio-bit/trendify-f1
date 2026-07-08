# A8-R110I2 — Local Catalog Intake -> Operator Workspace

## 1. Scope

Minimal local operator flow, all offline and deterministic:

```
real local CSV catalog
  -> synapse/ui/local_catalog_workspace.py (validation + honest statuses)
  -> deterministic unit economics (Decimal; operator numbers only)
  -> R109A-shaped candidate fixtures (candidates/*.json)
  -> existing ViewModel (operator_workbench_view_model.build_view_model)
  -> existing R109B workspace renderer (render_workspace_html)
  -> workspace.html + intake_report.json
```

No network, no live Dropi/Shopify/Meta, no credentials, no spend, no
fulfillment, no login. The only side effects are local files under the
chosen `--output-dir`. Same CSV bytes -> same output bytes (no timestamps,
no uuids, no runtime clock).

### CLI

```
python -m synapse.ui.local_catalog_workspace --csv <catalog.csv> --output-dir artifacts/a8_r110_local_catalog_workspace
```

Exit codes: `0` workspace generated; `2` file-level CSV error (missing file,
missing columns, no data rows); `3` no evaluable candidates (all rows
INVALID_INPUT — the intake report still explains why).

## 2. CSV contract (operator-facing)

Required header columns (values may be empty only where noted):

| Column | Required value? | Notes |
|---|---|---|
| `product_id` | yes | unique per file; duplicates are INVALID_INPUT |
| `title` | yes | product name shown in the workspace |
| `supplier` | yes | supplier label |
| `category` | header required, value optional | free text |
| `supplier_price_mxn` | optional value | empty -> INPUT_LOW |
| `shipping_cost_mxn` | optional value | empty -> INPUT_LOW |
| `sale_price_mxn` | optional value | empty -> INPUT_LOW; must be > 0 |

Optional columns: `payment_fee_mxn` (empty -> 0.00, documented default,
never a hidden markup), `source_url` (report-only, see 5), `notes`
(surfaces in the candidate's evidence notes).

## 3. Adapter mapping (CSV -> R109A fixture)

Explicit mapping; the financial semantics match the frozen R109A fixtures
(margin = price - cost - shipping - fee; breakeven CPA = margin):

| CSV column | Fixture field |
|---|---|
| `sale_price_mxn` | `economics.price_mxn` |
| `supplier_price_mxn` | `economics.product_cost_mxn` |
| `shipping_cost_mxn` | `economics.shipping_cost_mxn` |
| `payment_fee_mxn` | `economics.payment_fee_mxn` |
| computed | `economics.contribution_margin_mxn` / `_percent` / `breakeven_cpa_mxn` |
| `product_id`/`title`/`supplier`/`category` | `product.*` |
| `notes` | `evidence.notes[]` |

The full Dropi financial bridge (`dropi_catalog_eval_bridge`) is NOT used
here on purpose: it requires an `estimated_cac` assumption the operator has
not provided, and inventing a CAC would violate the no-invention rule. Unit
economics use only the operator's own CSV numbers.

`source_kind` is `operator_local_catalog_import` — never
`frozen_local_fixture`; provenance in the workspace names the CSV row.

## 4. Honest statuses

| Status | Meaning | Effect |
|---|---|---|
| `EVALUATING` | identity + all economics inputs valid | candidate with unit economics; `decision.outcome=EVALUATING`, `permission_gate=REVIEW` (never a recommendation) |
| `INPUT_LOW` | identity valid, key economics missing | candidate WITHOUT economics; nothing invented; missing fields listed in caveats and report |
| `INVALID_INPUT` | missing identity, non-numeric/negative money, non-positive sale price, duplicate `product_id`, or forbidden token in a fixture-bound field | excluded from the workspace; listed in `intake_report.json` with machine-readable reasons |

Every candidate keeps `operator_input` empty, so the ViewModel classifies
INPUT_LOW richness: marketing/shopify packs stay disabled and no claims or
copy are generated until the operator writes a real brief. `can_prepare`
stays false — no sell-prep affordances, no prepare CTA, no payload copy.

## 5. Offline HTML boundary

The workspace HTML is offline-static by contract (R109A forbidden-token
scan: no fetch-style calls, no XHR, no external script/link, no absolute
web URLs, no posting forms). Therefore:

- `source_url` never reaches the fixture or the HTML; it is preserved in
  `intake_report.json` only.
- Any fixture-bound text field containing a forbidden token marks the row
  INVALID_INPUT (`forbidden_token_in_field:<column>`) instead of silently
  rewriting operator text.

## 6. Outputs

Under `--output-dir` (default `artifacts/a8_r110_local_catalog_workspace/`):

- `workspace.html` — multi-candidate operator workspace (existing R109B
  renderer; localStorage-only session/drafts as documented in R109B 5d/5f).
- `candidates/a8_r110_<slug>.json` — one honest fixture per usable row.
- `intake_report.json` — deterministic report: schema version, counts,
  per-row status + reasons + `source_url`, and the declared boundary flags.

## 7. Tests

`tests/ui/test_a8_r110_local_catalog_workspace.py`: evaluated candidates
from the nominal CSV (Decimal-exact economics), honest workspace surface
(no prepare CTA / packs / payload copy), mixed CSV statuses incl.
INVALID_INPUT reasons, file-level errors, forbidden-token scans (HTML,
report, R110 sources), byte-identical determinism across runs, frozen
R109A fixtures still rendering, and CLI exit codes 0/2/3.
