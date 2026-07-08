# A8-R84 Release Boundary

Status: RELEASE_1_BOUNDARY

Base:
- Branch: feat/ui-read-model
- HEAD: 1006f648c6d3259297d89118c2c881c80c6781ee
- Subject: docs(method): close method foundation boundary

## Boundary Name

SYNAPSE Release 1 — Selling-Ready Manual Operator / Dry-Run Boundary

## Decision

Release 1 is allowed to support manual selling decisions.

Release 1 is not allowed to execute live external writes or automatic spend.

## Closed Capabilities

Release 1 includes:

- local-first operation;
- synthetic/product candidate discovery path;
- Decimal financial authority;
- marketing brief generation;
- decision record generation;
- spend/safety guard in sandbox;
- evidence and ledger-backed dry-run flow;
- read/operator surface sufficient for manual review;
- no known P1/P0 blocker from A8-R81, A8-R82, or A8-R83.

## Required Selling Mode

Selling must remain manual-operator controlled:

1. SYNAPSE may evaluate a product.
2. SYNAPSE may generate decision evidence.
3. SYNAPSE may generate marketing brief/angles.
4. Operator may manually choose product/channel.
5. Operator may manually publish/list/sell outside automated live writes.
6. Operator must manually verify supplier, price, stock, shipping, refund policy, and claims.
7. Operator must manually control ad spend.

## Hard Prohibitions

Release 1 prohibits:

- Shopify live product write;
- Dropi live order creation;
- Meta live campaign/ad/adset creation;
- automatic spend;
- automatic fulfillment;
- automatic customer-facing claims without operator review;
- bypassing hooks with --no-verify;
- using live credentials to mutate external systems.

## Known Non-Release-1 Work

The following are real SYNAPSE system work, but are not part of this Release 1 boundary:

- Shopify controlled live write path;
- Dropi controlled order path;
- Meta Ads controlled live campaign path;
- real connector read-only hardening;
- real sales outcome learning;
- premium/final UI;
- autopilot execution;
- commercial live-write release.

These move to Release 2 / Release 3 and must not reopen Release 1.

## Closed Blockers

- A8-R81 closed P1-A: Dropi order forwarder guard.
- A8-R82 closed P1-B: Decimal financial authority.
- A8-R83 closed method foundation boundary with no code patch required.

## Release 1 Exit Criteria

Release 1 can be considered closed when:

- this boundary file is committed;
- touched/critical files compile;
- A8-R82 money path tests pass;
- A8-R70 smoke integration passes;
- network/write guard tests pass;
- git status is clean;
- audit bundle is generated;
- external audit confirms boundary or reports only non-blocking notes.

## Cloud / Claude Rule

Cloud/Claude is not required to keep working locally.

Cloud/Claude becomes required only for final external boundary audit or if a new ambiguous P1/P0 appears.