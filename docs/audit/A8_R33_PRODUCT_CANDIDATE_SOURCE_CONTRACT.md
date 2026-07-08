# A8-R33 — Product Candidate Source Contract

## Purpose

A8-R33 defines how SYNAPSE accepts local product candidate source data before sending candidates into the A8-R32 product decision artifact CLI.

This island answers:

Where do candidate rows come from before product scoring?

## Contract

Input:

- local JSON object with rows or candidates
- local JSON list of candidate rows

Output:

- normalized candidates
- rejected rows with reasons
- source quality report
- source_sha256
- manual_champion_provided=false
- ready_for_product_decision_cli gate

## Non-goals

A8-R33 does not:

- scrape marketplaces
- call supplier APIs
- connect Shopify
- launch ads
- spend budget
- choose champion directly

A8-R33 only validates and normalizes candidate source rows.

## Hard Rules

- Source data cannot declare a champion.
- Duplicate SKUs are blocked.
- Scores must be 0-100.
- sell_price must exceed landed_cost.
- Candidates must contain the full A8-R31 field set.
- Output must be deterministic.
- Normalized candidates must be compatible with Product Decision Engine.

## Flow

candidate source
→ normalized candidate packet
→ product decision CLI
→ product decision artifact

## Claude Reentry Questions

When Claude returns, audit:

1. Is the source schema too strict or correctly protective?
2. Should rejected rows be recoverable through a repair pipeline?
3. Should source_sha256 hash raw bytes instead of canonical JSON?
4. Should this become a CLI in the next island?
5. Is this enough before connecting real ingestion sources?

## Acceptance

A8-R33 passes only if:

- source module compiles
- targeted tests pass
- full F1 gate passes
- exactly three files are staged
- no unstaged files remain
- no untracked files remain
- no commit is made during pre-gates
