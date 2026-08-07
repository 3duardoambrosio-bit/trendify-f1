# A8-R113.2 — Functional Truth Research and Repair Contract

## Status

- Review class: `INTERNAL_TECHNICAL_REVIEW`
- Scope: local/offline Workbench behavior only
- Live Shopify/Meta/Dropi: not authorized
- External writes, spend, fulfillment, publication: not authorized
- Staging/commit: not authorized by this island

## Problem confirmed from the rendered Workbench

The checkpoint pipeline was real, but the visual surface did not yet meet a
production functional-truth gate:

1. five filter buttons and four sort buttons were visible without handlers;
2. operator drafts persisted locally but did not update the effective preview
   or individual copy payloads;
3. the primary checkpoint action could route back to Command Center instead of
   the promised Evidence/Shopify destination;
4. a local alias/context gate could be mistaken for authentication;
5. passing reason codes could be painted as blockers;
6. `publication_not_authorized` was counted as a missing commercial input;
7. an economics PASS could be labelled WATCH because of non-economic input
   richness;
8. current checkpoint evidence was mixed with historical frozen-fixture
   provenance;
9. multi-candidate workspace documents contained repeated DOM ids;
10. keyboard and focus behavior was incomplete for tabs, local checks, candidate
    cards, rail navigation, and the Evidence drawer.

## Research basis

### Stable local origin

Browser behavior for `localStorage` under `file:` URLs is not a stable contract.
The production Workbench should ultimately run from a loopback origin such as
`http://127.0.0.1`, while remaining local-first and making no external network
requests. This island does not introduce the local server; it keeps the current
static artifact compatible and removes misleading behavior first.

### Persistence tiers

Small UI preferences can remain browser-local. Structured drafts, approvals,
and audit events should eventually use a transactional structured store such as
IndexedDB or a local application database. This island keeps the existing
storage boundary explicit and does not claim durable production persistence.

### Interaction semantics

The implementation follows the practical requirements behind the WAI-ARIA
Authoring Practices:

- buttons invoke a defined action;
- tab controls expose selected state and support arrow/Home/End navigation;
- the Evidence drawer behaves as a dialog with explicit focus entry, Escape
  close, and focus return;
- custom checkbox-like controls expose role, keyboard operation, and
  `aria-checked`;
- labels are programmatically associated with draft fields.

### Behavioral verification

The preferred production gate is a real browser matrix using Playwright role and
label locators, auto-retrying assertions, and accessibility scans. The included
pytest gate establishes deterministic source/markup contracts without adding a
runtime browser dependency to the repository. A separate controlled browser
probe was used while preparing this package.

## Implemented architecture

### Immutable system output vs effective local draft

The Workbench now distinguishes:

1. immutable system/ViewModel output;
2. browser-local operator draft;
3. effective local preview and individual payload;
4. full-pack system snapshot plus an explicit local override appendix.

Editing does not mutate the ViewModel, recalculate finance, pass Claim Guard,
authorize publication, or create an external write. It does update the local
preview and matching individual payload so the UI no longer silently copies a
stale value.

### Control behavior

- multi-candidate filters execute against `data-candidate-kind`;
- multi-candidate sorts execute against score, margin, risk, or state;
- filter/sort controls are not rendered for a single candidate;
- empty filter results display an explicit message;
- selected filter, sort, and candidate state are browser-local;
- every formal button/input/textarea has a recognized interaction contract;
- multi-candidate DOM ids and local references are scoped per candidate.

### Truthful boundaries

- the alias screen is called `Contexto local del operador`, not login/session;
- publication authorization is a deliberate boundary, not a missing field;
- passing reason codes are drivers, not blockers;
- economics status is derived from economics, not brief richness;
- a zero-item blocked queue can still explain that the candidate is unready;
- Learning remains explicitly non-operational until real observations exist.

### Provenance

Historical fixtures retain their frozen R109A defaults. Newer adapters may
supply a constrained provenance override for adapter status, code head, phase
status, island, and worktree state. The checkpoint adapter records current HEAD
and whether source changes are present; this does not falsely claim a clean
commit for uncommitted code.

## Functional-truth gate

The island is acceptable only when all of the following pass in the real repo:

```text
PY_COMPILE=PASS
TARGETED_PYTEST=PASS
CHECKPOINT_SUITE=PASS
DETERMINISM=PASS
GIT_DIFF_CHECK=PASS
STAGED_ENTRY_COUNT=0
COMMIT_PERFORMED=false

DEAD_FILTER_CONTROLS=0
DEAD_SORT_CONTROLS=0
FORMAL_CONTROLS_WITHOUT_CONTRACT=0
DUPLICATE_DOM_IDS_WORKSPACE=0
DRAFT_PREVIEW_PARITY=PASS
DRAFT_INDIVIDUAL_PAYLOAD_PARITY=PASS
PRIMARY_ACTION_TARGET=PASS
PUBLICATION_BOUNDARY_SEPARATION=PASS
PASS_CODES_NOT_BLOCKERS=PASS
ECONOMICS_STATUS_SEPARATION=PASS
PROVENANCE_CURRENT_ADAPTER=PASS
KEYBOARD_AND_DRAWER_SEMANTICS=PASS
```

## Deferred deliberately

The following are not smuggled into this repair:

- real authentication or authorization;
- a loopback application server;
- IndexedDB migration;
- approval/signature workflow;
- Shopify, Meta, or Dropi live connectors;
- external publication, spend, fulfillment, or analytics;
- production-grade multi-user concurrency.

Those require separate islands and explicit gates.
