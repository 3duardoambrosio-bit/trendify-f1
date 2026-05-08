# A8-R36 — Product Candidate Pipeline Golden Fixtures

## Objective

A8-R36 adds deterministic golden fixture coverage for the local product candidate pipeline.

The scope validates local candidate source inputs through normalization, decisioning, and pipeline materialization without manual champion selection, network access, Shopify writes, Meta/Facebook calls, scraping, or product launch behavior.

## Files Added

| Type | Path |
|---|---|
| valid fixture | `tests/fixtures/product_candidate_sources/a8_r36_valid_winning_batch.json` |
| mixed fixture | `tests/fixtures/product_candidate_sources/a8_r36_mixed_quality_batch.json` |
| empty fixture | `tests/fixtures/product_candidate_sources/a8_r36_invalid_empty_batch.json` |
| manifest golden | `tests/golden/product_candidate_pipeline/expected_manifest_valid_winning_batch.json` |
| decision golden | `tests/golden/product_candidate_pipeline/expected_decision_valid_winning_batch.json` |
| source golden | `tests/golden/product_candidate_pipeline/expected_source_valid_winning_batch.json` |
| targeted test | `tests/ops/test_a8_r36_product_candidate_pipeline_golden_fixtures.py` |

## Source Contract

Required candidate fields:

``text
sku
name
niche
landed_cost
sell_price
shipping_days
supplier_score
demand_score
saturation_score
content_fit_score
problem_severity_score
compliance_risk_score
return_risk_score
``

Score fields are validated in the 0..100 range.

## CLI Contract

``text
tools/product_candidate_pipeline_cli.py --input <fixture.json> --output-dir <output_dir> --pretty
``

## Verified Scenarios

| Scenario | Expected result |
|---|---|
| valid winning batch | pipeline succeeds and emits exactly 3 output JSON files |
| mixed quality batch | pipeline succeeds, preserves 2 valid rows, rejects 2 invalid rows |
| empty batch | pipeline fails in controlled mode without traceback |

## Acceptance Evidence

| Check | Value |
|---|---:|
| targeted pytest result | `3 passed` |
| targeted pytest stderr bytes | `0` |
| test function count | `3` |
| test UTF-8 BOM count | `0` |
| test UTF-16 BOM count | `0` |
| fixture/golden JSON UTF-8 BOM count | `0` |
| fixture/golden JSON UTF-16 BOM count | `0` |
| valid normalized candidates | `3` |
| valid rejected rows | `0` |
| mixed normalized candidates | `2` |
| mixed rejected rows | `2` |
| valid champion SKU | `A8R36-CHAMPION-001` |
| mixed champion SKU | `A8R36-MIXED-CHAMPION-001` |
| manifest hash path count | `2` |
| network marker hit count | `0` |

## Non-Scope

- no scraping
- no paid APIs
- no Shopify writes
- no Meta/Facebook ads
- no product launch
- no manual champion override
- no manual champion selection

## Git Notes

The repository ignores `*.json` globally via `.gitignore`, so the six intended JSON artifacts must be staged with `git add -f`.

The expected staged file count for this unit is exactly 8.
