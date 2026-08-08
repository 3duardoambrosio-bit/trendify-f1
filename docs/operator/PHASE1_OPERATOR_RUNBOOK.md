# SYNAPSE Phase 1 - Operator Runbook

## Purpose

This is the practical Phase 1 operating path.

The launcher does not create a new decision engine. It calls the existing,
audited local operator-enrichment flow and produces the local workspace.

Phase 1 remains operator-controlled and local-first.

## Construction freeze

After this operationalization block is merged, Phase 1 construction is frozen.

New product/source construction is not authorized unless a concrete P0/P1
finding requires repair.

P2 notes are recorded for later maintenance and do not reopen construction by
themselves.

This runbook does not authorize Phase 2.

It does not authorize:

- live Shopify writes;
- live Dropi writes or order forwarding;
- live Meta publishing;
- real ad spend;
- fulfillment automation;
- autonomous product discovery;
- external network enrichment.

## 1. Prepare a local CSV

Required headers:

```text
product_id
title
supplier
category
supplier_price_mxn
shipping_cost_mxn
sale_price_mxn
```

Optional headers:

```text
payment_fee_mxn
source_url
notes
```

Example:

```csv
product_id,title,supplier,category,supplier_price_mxn,shipping_cost_mxn,sale_price_mxn,payment_fee_mxn,source_url,notes
op_001,Producto Operador,Proveedor Local,hogar,100.00,50.00,299.00,10.00,,
```

Use only information you actually know.

Do not paste credentials, tokens, secrets, unsupported claims, or web content
into fixture-bound text.

## 2. Start SYNAPSE

From the repository root:

```powershell
.\START_SYNAPSE.ps1 -Csv .\catalogo.csv
```

Default workspace:

```text
artifacts/operator_workspace
```

The launcher:

1. validates that the CSV is a local file;
2. locates Python 3.10+;
3. explicitly sets Phase 1 live/write flags OFF while the local flow runs;
4. calls the existing `synapse.ui.operator_enrichment_cli rebuild`;
5. verifies `workspace.html` and `intake_report.json`;
6. opens the local HTML unless `-NoOpen` is supplied;
7. restores the caller's previous process environment before returning.

For validation without opening a browser:

```powershell
.\START_SYNAPSE.ps1 -Csv .\catalogo.csv -NoOpen
```

## 3. Read the first workspace

The initial rebuild may show a candidate without operator enrichment.

That is expected.

Possible enrichment states include:

- `ABSENT`
- `PARTIAL`
- `INVALID_INPUT`
- `BLOCKED`
- `FALLBACK`
- `ACCEPTED`

No state is permission to publish automatically.

The operator remains the decision maker.

## 4. Create an enrichment template

Find the candidate fixture id under:

```text
artifacts/operator_workspace/candidates
```

Create its template:

```powershell
python -m synapse.ui.operator_enrichment_cli template `
  --workspace .\artifacts\operator_workspace `
  --fixture-id <fixture_id>
```

The editable file is created under:

```text
artifacts/operator_workspace/candidates_input
```

The normal template command does not overwrite existing operator work.

## 5. Add real operator context

Provide only context you can support.

R109 richness is fed by:

- buyer_pain
- target_audience
- objections
- proof_available
- desires
- differentiators
- market_context
- customer_language

Methodology context also includes:

- product_facts
- buyer_state
- claim_risk_hints
- channel
- margin_profile

Eight complete richness fields produce `INPUT_RICH`.
Four to seven produce `INPUT_PARTIAL`.
Fewer than four produce `INPUT_LOW`.

Do not fill fields merely to force `INPUT_RICH`.

## 6. Rebuild

Run the same launcher again:

```powershell
.\START_SYNAPSE.ps1 -Csv .\catalogo.csv
```

The existing enrichment files remain under `candidates_input`.

Review:

```text
workspace.html
intake_report.json
candidates/*.json
```

## 7. Interpret the result honestly

`ACCEPTED` with `INPUT_RICH` can unlock the existing local full-pack surfaces.

`BLOCKED`, `FALLBACK`, `PARTIAL`, `INPUT_LOW`, or `INVALID_INPUT` are not
failures to hide. They are operator states that require review or more truthful
input.

Commercial copy is not authorized when the methodology blocks it.

`decision.permission_gate=REVIEW` remains the operative boundary.

## 8. Phase 1 boundary

The launcher is a local convenience layer only.

It must not become:

- a network client;
- a publisher;
- an order forwarder;
- a spend executor;
- a credential loader for live services;
- a second marketing or financial engine.

When Phase 1 operationalization is closed, use SYNAPSE as an operator before
authorizing new construction.

Only a concrete P0/P1 may break the construction freeze.
