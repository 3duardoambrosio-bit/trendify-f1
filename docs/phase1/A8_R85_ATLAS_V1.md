# A8-R85 Atlas V1

Status: ATLAS_V1

## 1. Purpose

Atlas V1 is the operational truth map after Release 1 closure.

Atlas V1 is not a feature island, not a UI island, not a connector island, and not a new total audit.

Its job is to prevent circular diagnosis by recording:

- what exists;
- what is closed;
- what remains prohibited;
- what belongs to Release 2;
- what belongs to Release 3;
- what must happen immediately next.

## 2. Custody

- Branch: feat/ui-read-model
- Base HEAD: 8529d58dd69337df1dc27c6f72fba1ef5fdf094d
- Base subject: docs(release): record release 1 external audit close
- Release 1 close record: docs/phase1/A8_R84_RELEASE_1_CLOSE_RECORD.md
- Release 1 boundary: docs/phase1/A8_R84_RELEASE_BOUNDARY.md
- Method boundary: docs/phase1/A8_R83_METHOD_FOUNDATION_DECISION.md

## 3. Release 1 Closed Boundary

Release 1 is closed with notes as:

- operator-in-control;
- local-first;
- dry-run;
- no live writes;
- no automatic spend;
- no automatic fulfillment.

Release 1 allows SYNAPSE to support commercial preparation, not to execute live external mutations.

## 4. Hard Prohibitions Still Active

The following remain prohibited:

- Shopify live product write;
- Dropi live order creation;
- Meta live campaign/ad/adset creation;
- Google Ads live mutation;
- automatic spend;
- automatic fulfillment;
- claims published without operator review;
- live credentials mutating external systems;
- bypassing hooks with --no-verify.

## 5. Real Subsystem Inventory

| Subsystem | Current status | Release meaning |
|---|---|---|
| Financial authority | CLOSED for Release 1 | Decimal money path is the authority for evaluated financial decisions. |
| Dropi order forwarder guard | CLOSED for Release 1 | Live order mutation is fail-closed under default posture. |
| Spend / write guards | CLOSED for Release 1 | Live mutation/spend remains blocked. |
| R70 smoke integration | CLOSED for Release 1 | Synthetic flow chains discovery, financial evaluation, marketing brief, decision, and spend guard. |
| Evidence / ledger pattern | PRESENT | Supports auditability of dry-run/operator-in-control decisions. |
| UI/read model | EARLY | Useful for review, not yet an operator console. |
| Marketing brief base | PRESENT_BUT_NOT_EXPERT | Produces base materials, not certified expert campaign strategy. |
| Ranker / scoring | HEURISTIC | Non-blocking for Release 1; not certified as optimal method foundation. |
| Thompson / Bayesian methods | DORMANT_OR_PARTIAL | Must not be claimed as active commercial decision authority yet. |
| Learning loop | TECHNICALLY_PRESENT | Cannot become real until outcomes exist. |
| Dropi/Shopify/Meta/Google live connectors | NOT_READY | Release 2/3 only after dedicated readiness gates. |

## 6. Operator-In-Control Definition

Operator-in-control does not mean traditional manual selling.

It means:

- SYNAPSE prepares the commercial operation;
- SYNAPSE evaluates and documents the decision;
- SYNAPSE generates the base marketing/evidence package;
- the operator controls external buttons until live writes are audited and authorized.

Eduardo should not invent strategy from scratch.

Eduardo may still:

- approve product/provider information;
- publish externally;
- enter budget externally;
- create or paste campaign settings externally;
- record outcomes;
- stop anything that looks wrong.

## 7. Real Gaps To List Without Reopening Release 1

These gaps are real, but they do not reopen Release 1:

1. Marketing Expert Foundation is not certified.
2. Campaign structure does not yet encode a serious Campaign -> Ad Set -> Ad execution pack.
3. Google Ads is not modeled as a separate paid-media lane.
4. Meta Ads live execution is not authorized.
5. Dropi read-only real ingestion is not built as a Release 2 source.
6. Shopify listing prep/dry-run is not built as an operator artifact.
7. Operator Console is not yet a full product -> evaluation -> marketing -> decision -> action flow.
8. Ranker still uses heuristic weighting.
9. Thompson/Bayesian methods are not fully activated into the commercial loop.
10. Learning cannot be validated until real outcomes exist.
11. Product discovery still needs real source ingestion beyond synthetic fixtures.
12. Live-readiness audit is required before any external mutation.

## 8. Release Matrix

| Release | Allowed | Prohibited |
|---|---|---|
| Release 1 | operator-in-control, dry-run, local evaluation, evidence, base briefs, safety guards | live writes, spend automation, fulfillment automation |
| Release 2 | Marketing Expert Foundation, Operator Console, read-only connectors, listing prep, campaign prep, outcome ledger | live mutation without dedicated gate |
| Release 3 | controlled writes, controlled spend, fulfillment, autopilot, outcome learning | unbounded spend, unreviewed claims, unguarded credentials |

## 9. Immediate Next Island

The next island after Atlas must be:

A8-R86 Marketing Expert Foundation.

Reason:

Marketing Expert Foundation is the highest-value local work after Release 1 closure.

It does not require live connectors, spend, fulfillment, Shopify writes, Dropi writes, or Meta writes.

It directly addresses the core requirement:

SYNAPSE must provide expert-level commercial direction so Eduardo does not invent marketing strategy from scratch.

## 10. Atlas Non-Goals

Atlas must not:

- touch production code;
- create UI;
- connect Dropi;
- connect Shopify;
- connect Meta;
- connect Google Ads;
- modify financial authority;
- activate dormant rankers;
- rewrite marketing;
- reopen Release 1;
- become a roadmap monster.

## 11. Close Criteria

A8-R85 closes when:

- this Atlas document exists;
- one coherence test verifies the document and referenced artifacts;
- no production code is modified;
- git status is clean after commit;
- next island is explicitly A8-R86 Marketing Expert Foundation.