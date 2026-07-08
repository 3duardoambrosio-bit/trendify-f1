# A8-R32 — Product Decision Artifact CLI Contract

## Purpose

A8-R32 converts the A8-R31 in-memory Product Decision Engine into an executable artifact contract.

SYNAPSE must be able to receive product candidate JSON and emit a deterministic decision artifact JSON.

## Contract

Input:

- JSON object with candidates, constraints, optional weights, and backup_count
- or raw JSON list of candidates

Output:

- product decision packet
- champion
- backups
- rejected candidates
- numeric score
- score components
- block reasons
- constraints
- weights
- deterministic input_sha256
- manual_selection_used=false
- quality gates

## Non-goals

A8-R32 does not:

- connect live supplier APIs
- scrape products
- launch ads
- spend budget
- create Shopify products
- select a real product from live market data

## Why this matters

A8-R31 proved the system can score candidates.
A8-R32 proves the system can produce an artifact that another process can audit, store, and pass to the next stage.

This moves SYNAPSE from library behavior toward operational workflow.

## Acceptance

A8-R32 passes only if:

- CLI compiles
- targeted CLI tests pass
- full F1 gate passes
- exactly three files are staged
- no unstaged files remain
- no untracked files remain
- no commit is made during pre-gates

## Claude Reentry Questions

When Claude returns, audit:

1. Is this artifact schema strong enough for supplier ingestion?
2. Should input_sha256 cover raw bytes instead of canonical normalized input?
3. Are the quality gates sufficient before connecting live product sources?
4. Does this preserve the rule that Lalo is not the manual selector?
5. What should A8-R33 add before real candidate ingestion?
