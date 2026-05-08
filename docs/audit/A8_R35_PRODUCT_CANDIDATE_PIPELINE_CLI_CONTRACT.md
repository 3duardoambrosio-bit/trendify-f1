# A8-R35 — Product Candidate Pipeline CLI Contract

## Purpose

A8-R35 creates the first local end-to-end commerce decision pipeline.

It chains:

1. local product candidate source JSON
2. candidate source normalization
3. product decision artifact generation
4. pipeline manifest generation

## Flow

source JSON
→ product_candidate_pipeline_cli.py
→ normalized_candidate_source.json
→ product_decision_artifact.json
→ product_candidate_pipeline_manifest.json

## Contract

Input:

- local JSON object with `rows` or `candidates`
- or local JSON list of candidate rows

Output directory:

- normalized_candidate_source.json
- product_decision_artifact.json
- product_candidate_pipeline_manifest.json

## Hard Rules

A8-R35 does not:

- scrape marketplaces
- call supplier APIs
- call Shopify
- create products
- run ads
- spend budget
- accept manual champion override

The pipeline is local-only and deterministic.

## Acceptance

A8-R35 passes only if:

- pipeline CLI compiles
- targeted pipeline tests pass
- full F1 gate passes
- exactly three files are staged
- no unstaged files remain
- no untracked files remain
- no commit is made during pre-gates

## Claude Reentry Questions

When Claude returns, audit:

1. Is this pipeline enough to prove local end-to-end candidate decision flow?
2. Should the next island add fixture-based sample sources?
3. Should source_sha256 hash raw bytes rather than canonical JSON?
4. Should output paths include run IDs?
5. Is the no-manual-selection rule enforced across all pipeline layers?
