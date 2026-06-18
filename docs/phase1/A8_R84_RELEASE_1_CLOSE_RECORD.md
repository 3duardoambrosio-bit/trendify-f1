# A8-R84C Release 1 External Close Record

Status: RELEASE_1_CLOSED_WITH_NOTES

## Base

- Branch: feat/ui-read-model
- HEAD: 5567e65c7c7735ae082a7a578e67c49ab5108636
- Subject: docs(release): define selling-ready boundary
- Boundary doc: docs/phase1/A8_R84_RELEASE_BOUNDARY.md

## External Audit Result

- Auditor: Claude external audit
- Verdict: PASS_WITH_NOTES
- Confidence: 88
- Final decision: Release 1 can be closed as operator-in-control / dry-run / no live writes / no automatic spend / no automatic fulfillment.
- Release 1 status: CLOSEABLE
- P0 blockers: NONE
- P1 blockers: NONE

## What Release 1 Means

Release 1 is closed only as a safe operator-in-control commercial support boundary.

Release 1 allows SYNAPSE to support commercial work by:

- evaluating products;
- using Decimal financial authority;
- generating evidence and decision records;
- generating base marketing briefs;
- preserving safety/spend/write guards;
- supporting operator-controlled execution.

Release 1 does not mean SYNAPSE is fully automated or live-connected.

## Hard Prohibitions Still Active

Release 1 does not authorize:

- Shopify live product writes;
- Dropi live order creation;
- Meta live campaign/ad/adset creation;
- Google Ads live mutation;
- automatic spend;
- automatic fulfillment;
- customer-facing claims without operator review;
- live credentials mutating external systems;
- bypassing hooks with --no-verify.

## External Audit Evidence

The external auditor reported:

- 65/65 release gate tests passed independently.
- Dropi fail-closed under default Release 1 posture.
- Money path fail-closed on invalid financial input.
- Shopify and Meta network guard probes blocked.
- Zero external IO under the tested boundary posture.
- R81 Dropi guard persisted.
- R82 Decimal money-path fix persisted.
- R83 method foundation decision was acceptable for Release 1 scope.
- A8-R84 boundary doc was honest and correctly scoped.

## Custody Note

The external auditor flagged a custody discrepancy:

- the prompt-declared pack name/hash did not match the uploaded outer pack audited by Claude;
- the auditor reported an outer hash prefix mismatch: declared EF1B7ABA... versus audited e680c57b...;
- the auditor still found all 10 expected entries and audited the internal repo_at_head.zip tree;
- the internal repo tree was consistent with HEAD 5567e65c7c7735ae082a7a578e67c49ab5108636 and the R82 -> R83 -> R84 chain.

This is recorded as a custody note, not a P0/P1 blocker.

## Method Foundation Note

R83 closed the method foundation question only for Release 1.

This does not certify that SYNAPSE already has the final best possible commercial methods.

Known non-blocking method gaps remain:

- Marketing Expert Foundation is not yet certified.
- Ranker still contains heuristic weighting.
- Thompson/Bayesian methods exist but are not fully activated/cabled into the commercial decision loop.
- Learning loop cannot become real until outcomes exist.

These are Release 2/3 work and must not be confused with Release 1 closure.

## Closure Decision

Release 1 is closed with notes.

Closure scope:

- operator-in-control;
- local-first;
- dry-run;
- no live writes;
- no automatic spend;
- no fulfillment automation.

Next island:

- A8-R85 Atlas V1, after this close record.
- A8-R86 Marketing Expert Foundation should follow Atlas because marketing expert capability is not yet certified and is core to the intended SYNAPSE value.

## Do Not Reopen Release 1 For

- UI premium;
- live connectors;
- live writes;
- Meta/Google Ads mutation;
- Dropi order mutation;
- Shopify product mutation;
- outcome learning;
- method optimization;
- Marketing Expert Foundation.

Those belong to the next releases/islands.