# Operational Readiness Checklist

Status: pre-live gate
Scope: SYNAPSE / Trendify Fase 1
Rule: no live API, no real ad spend, no real customer-facing launch unless every required item is explicitly checked.

Allowed values: check, no-check, deferred.

A go decision is invalid if any required item is no-check.

## Required checklist

| ID | Item | Responsible | Status | Evidence required | Go blocker |
|---:|---|---|---|---|---|
| 01 | Facebook Business Page exists and is controlled by the operator | human | no-check | Page URL or internal evidence reference | yes |
| 02 | Instagram Business account is connected to the Facebook Page | human | no-check | IG handle and connection screenshot/reference | yes |
| 03 | Meta Business Manager / ad account ownership is verified enough for intended test scope | human | no-check | Business/ad account reference; no secrets | yes |
| 04 | Shopify store exists and target theme/channel is ready for test traffic | human | no-check | Store admin reference; no token in docs | yes |
| 05 | Shopify Custom App or Admin API access plan is defined without exposing token values | human | no-check | App name, scopes, token storage path; no token value | yes |
| 06 | Webhook secret handling path is defined and tested with synthetic value only | system | no-check | Synthetic validation output or test evidence | yes |
| 07 | Dropi or supplier credentials path is defined without exposing real credential values | human | no-check | Credential storage path; no credential value | yes |
| 08 | First SKU is selected with margin, supplier, shipping, refund, and stock assumptions documented | human | no-check | SKU decision sheet/document reference | yes |
| 09 | Creative assets for first campaign are produced and reviewed | human | no-check | Asset folder/reference and approval status | yes |
| 10 | Initial capital cap and per-campaign risk cap are declared before any spend | human | no-check | Numeric budget cap and stop-loss value | yes |
| 11 | Kill switch / pause path is verified before live campaign execution | system | no-check | Executable evidence required: tests/p0/test_kill_switch_e2e_v1.py PASS; documented manual procedure alone is insufficient | yes |
| 12 | Monitoring runbook exists for first live window | system | no-check | Runbook reference with metrics and response owner | yes |
| 13 | Customer support path is defined before customer-facing traffic | human | no-check | Email/DM/channel and response SLA | yes |
| 14 | Refund / cancellation process is documented | human | no-check | Refund workflow reference | yes |
| 15 | Final human go/no-go template is completed and signed | human | no-check | Completed go/no-go document | yes |

## Minimum go criteria

- required checklist items marked check: 15
- required checklist items marked no-check: 0
- required checklist items marked deferred: 0 unless explicitly accepted with compensating control and owner
- real secrets pasted in chat/docs: 0
- live spend before signed go/no-go: 0
- human sign-off present: 1

## Explicit non-go states

Do not proceed if SKU is not selected, creatives are not ready, capital cap is not declared, stop-loss is not declared, kill switch is not verified, real tokens or credentials are requested in chat, Meta/Shopify/supplier setup is incomplete, or the operator cannot explain the decision in writing.

## Evidence discipline

Evidence may reference files, screenshots, logs, or internal notes, but must not include access tokens, API secrets, webhook secrets, passwords, private keys, customer personal data, or payment data.
