# A8-R31 — Product Decision Engine Contract

## Purpose

A8-R31 starts the commercial decision layer without launching, spending, or selecting a real product manually.

The contract is:

- The operator defines constraints.
- SYNAPSE evaluates product candidates.
- SYNAPSE produces a champion, backups, rejected candidates, scores, and reasons.
- Manual product picking is not the primary flow.
- The result must be deterministic and auditable.

## Non-goals

A8-R31 does not:

- launch a store
- spend ad budget
- pick a real market product from live sources
- connect to supplier APIs
- connect to Meta/TikTok/Shopify
- replace later Claude audit

## Required Product Decision Output

The engine must return:

1. champion candidate
2. ranked backups
3. rejected candidates
4. numeric score
5. score components
6. block reasons
7. constraints used
8. weights used
9. explicit marker that manual selection was not used

## Product Selection Rule

Lalo is not the primary product selector.

SYNAPSE must evaluate candidates with constraints and produce the decision packet. Lalo may approve or reject gates at early stages, but manual product selection is a fallback, not the operating model.

## Claude Reentry Questions

When Claude returns, audit:

1. Is this Product Decision Engine too static?
2. Are the scoring weights commercially sane?
3. What missing variables should be added before real supplier/product ingestion?
4. Is manual selection fully prevented as primary flow?
5. Does the contract move SYNAPSE toward autonomous product selection without premature launch risk?

## Acceptance

A8-R31 passes only if:

- targeted test passes
- full F1 gate passes
- exactly three files are staged
- no unstaged files remain
- no untracked files remain
- no commit is made during pre-gates
