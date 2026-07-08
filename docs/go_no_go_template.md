# Go / No-Go Template

Status: required before operational execution
Scope: SYNAPSE / Trendify Fase 1
Rule: this document must be completed by a human before live API activation, live ads, or real spend.

## Decision header

| Field | Value |
|---|---|
| Date | TODO |
| Operator | TODO |
| Branch | TODO |
| HEAD | TODO |
| PC_READY_SCORE | TODO |
| Decision | NO-GO |
| Decision owner | human |
| Human signature | TODO |
| Signature timestamp (UTC ISO 8601) | TODO |
| GO valid until (UTC ISO 8601, max 72h after signature) | TODO |
| Template HEAD at signature | TODO |

## Technical state

| Gate | Required value | Actual value | Pass |
|---|---:|---:|---|
| Full test suite RC | 0 | TODO | no-check |
| Worktree clean | 1 | TODO | no-check |
| Current HEAD recorded | 1 | TODO | no-check |
| Evidence ZIP available | 1 | TODO | no-check |
| No live secrets exposed in docs/chat | 1 | TODO | no-check |
| No live spend executed before sign-off | 1 | TODO | no-check |

## Operational state

| Gate | Required value | Actual value | Pass |
|---|---:|---:|---|
| Facebook Page ready | 1 | TODO | no-check |
| Instagram Business connected | 1 | TODO | no-check |
| Shopify store ready | 1 | TODO | no-check |
| Supplier / Dropi path ready | 1 | TODO | no-check |
| First SKU selected | 1 | TODO | no-check |
| Creatives ready | 1 | TODO | no-check |
| Monitoring runbook ready | 1 | TODO | no-check |
| Kill switch verified by executable test | 1 | TODO | no-check |
| Customer support path ready | 1 | TODO | no-check |
| Refund process documented | 1 | TODO | no-check |

## Capital and risk

| Field | Value |
|---|---:|
| Capital reserved | TODO |
| Capital allowed to risk | TODO |
| Daily spend cap | TODO |
| Campaign spend cap | TODO |
| Stop-loss amount | TODO |
| Stop-loss condition | TODO |
| Maximum acceptable loss before pause | TODO |
| Review frequency | TODO |

## First SKU decision

| Field | Value |
|---|---|
| SKU name | TODO |
| Supplier | TODO |
| Sale price | TODO |
| Unit cost | TODO |
| Gross margin | TODO |
| Shipping assumption | TODO |
| Refund assumption | TODO |
| Stock assumption | TODO |
| Primary buyer angle | TODO |
| Main risk | TODO |

## Pause criteria

| Condition | Threshold | Owner |
|---|---:|---|
| Spend exceeds declared cap | TODO | human |
| Campaign enters unexpected live state | any | system |
| API returns unknown contract drift | any | system |
| Customer issue cannot be resolved | any unresolved blocker | human |
| Supplier stock/price changes materially | any material change | human |
| Tracking is not working | any | system |

## Final decision

Choose one: GO, NO-GO, HOLD, PATCH FIRST.

Decision: NO-GO

Reason: TODO

Human signature: TODO

## Non-negotiable rule

A GO is invalid unless every required operational gate is checked, capital and stop-loss are numeric, first SKU is named, kill switch is verified by executable evidence, human signature is present, Signature timestamp is present, GO valid until is present, GO validity is at most 72 hours from signature, Template HEAD at signature is recorded, and no real secrets are written into this document.

## Signature validity

A GO decision is valid only when:

- Signature timestamp is written in UTC ISO 8601 format
- GO valid until is written in UTC ISO 8601 format
- GO valid until is no more than 72 hours after Signature timestamp
- Template HEAD at signature is recorded
- Any material change to code, checklist, SKU, budget, account setup, supplier setup, kill switch, or evidence invalidates the prior GO
