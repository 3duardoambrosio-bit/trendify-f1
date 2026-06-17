# A8-R83 Method Foundation Decision

Status: NO_CODE_PATCH_REQUIRED

Base:
- Branch: feat/ui-read-model
- HEAD: cccde3d9cebc72705d409735b4c7886b2398686b
- Subject: fix(financial): route catalog decisions through decimal engine

Source:
- Locator report: C:\Users\edu_a\OneDrive\Documentos\trendify-fase1\runs\a8_r83_method_foundation_grep_v2_20260617_021034\a8_r83_method_foundation_grep_report.txt
- Smoke tests: 9/9 PASS
- Repo status before decision: clean outside runs/

## Decision

A8-R83 does not require a code patch for Release 1.

Reason:
- The grep locator surfaced method/scoring/decision terms, but no P1/P0 blocker that prevents selling-ready Release 1.
- The remaining hits are classified as non-blocking for the current boundary:
  - score/confidence float values used for non-money ranking or UI display;
  - tests and fixtures;
  - deprecated or compatibility functions;
  - Meta/Shopify/Dropi live-path tests that remain outside Release 1;
  - marketing quality heuristics that do not override financial authority.
- The previously confirmed blockers are already closed:
  - A8-R81: Dropi write guard P1-A closed.
  - A8-R82: Decimal financial authority P1-B closed.

## Release 1 Scope

Release 1 remains:

- local-first;
- dry-run;
- no live external writes;
- no real ad spend;
- manual-operator selling support;
- Decimal financial decision authority;
- evidence/ledger-backed dry-run flow.

## Explicit Non-Blockers for Release 1

The following do not block A8-R84 boundary:

- Shopify live writes;
- Dropi live order creation;
- Meta live campaign creation;
- fully automated autopilot;
- real outcome learning loop;
- premium/final UI;
- additional scoring optimization;
- legacy/deprecated files not on the Release 1 execution path.

## Next

Proceed to A8-R84 Release Boundary.

A8-R84 must define:
- what is closed;
- what is allowed for manual selling;
- what remains prohibited;
- what moves to Release 2.