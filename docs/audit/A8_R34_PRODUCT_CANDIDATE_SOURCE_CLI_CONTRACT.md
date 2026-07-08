# A8-R34 — Product Candidate Source CLI Contract

## Purpose

A8-R34 converts the A8-R33 Product Candidate Source module into an executable CLI contract.

The system can now transform a local product candidate source JSON into a normalized candidate artifact JSON that is ready for the A8-R32 Product Decision CLI.

## Flow

source JSON
→ product_candidate_source_cli.py
→ normalized candidate source artifact JSON
→ product_decision_cli.py
→ product decision artifact JSON

## Contract

Input:

- local JSON object with `rows` or `candidates`
- or local JSON list of candidate rows

Output:

- artifact_version
- source_contract_version
- source_id
- source_sha256
- candidates
- rejected_rows
- source_quality_report
- quality_gates
- manual_champion_provided=false
- ready_for_product_decision_cli gate

## Non-goals

A8-R34 does not:

- scrape marketplaces
- call supplier APIs
- create Shopify products
- run ads
- spend budget
- select champion directly

It only normalizes source data as an executable artifact.

## Acceptance

A8-R34 passes only if:

- source CLI compiles
- targeted CLI tests pass
- full F1 gate passes
- exactly three files are staged
- no unstaged files remain
- no untracked files remain
- no commit is made during pre-gates

## Claude Reentry Questions

When Claude returns, audit:

1. Is the source CLI artifact schema sufficient for future supplier ingestion?
2. Should source_sha256 hash raw bytes instead of canonical JSON?
3. Should rejected rows support repair recommendations?
4. Should the next island chain source CLI output directly into decision CLI in one orchestrated command?
5. Is the no-manual-champion rule strong enough across the source and decision layers?
