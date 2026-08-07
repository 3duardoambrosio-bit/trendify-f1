# A8-R112I2 — Operator-Approved Customer Copy Contract

## 1. Purpose

A8-R112I2 introduces an explicit customer-copy boundary for the local
storefront preview created by A8-R112I1.

It does not generate copy. It validates copy supplied by an operator and binds
approval to the exact canonical copy bytes through SHA-256 custody.

## 2. Safety boundary

The approval scope is permanently limited to `LOCAL_PREVIEW_ONLY`.

It does not authorize Shopify or Meta publication, Dropi calls, checkout,
external writes, spend, campaign creation, fulfillment, or any live operation.

The storefront safety envelope remains false and every product continues to
emit `publication_status = "NOT_AUTHORIZED"`.

## 3. No automatic projection

The following remain internal and cannot be transformed automatically into
customer-facing copy:

- methodology `safe_output`;
- hooks, scripts, CTA guidance, and channel guidance;
- offer or margin guidance;
- blocked reasons;
- buyer state and claim risk;
- supplier identity;
- financial fields;
- candidate output.

An accepted methodology decision is only a prerequisite for attaching approved
copy. It is not the source of that copy and is not publication authorization.

## 4. Optional item field

The R112 item may contain the optional exact field
`customer_copy_approval`. The original required fields remain `fixture` and
`methodology_context`. Unknown item fields continue to fail closed.

## 5. Approval envelope

```json
{
  "copy": {
    "product_id": "cat-001",
    "title": "Operator-approved title",
    "description": "Operator-approved description",
    "facts": ["Operator-approved public fact"],
    "proof": ["Operator-approved public proof statement"]
  },
  "approval": {
    "status": "APPROVED_FOR_LOCAL_PREVIEW",
    "scope": "LOCAL_PREVIEW_ONLY",
    "approved_copy_sha256": "<64 lowercase hexadecimal characters>",
    "publication_authorized": false,
    "external_writes_authorized": false
  }
}
```

Both mappings require exact keys. Missing and unknown fields fail closed.

## 6. Canonical copy custody

The approved digest is calculated only from the canonical `copy` mapping.

Canonical serialization uses UTF-8, sorted keys, compact separators,
`ensure_ascii=False`, `allow_nan=False`, and one final newline. Text is stripped
at its outer boundaries before hashing. Mapping insertion order does not change
the digest. Any copy mutation invalidates approval.

## 7. Binding and prerequisites

Approved copy is accepted only when:

1. `copy.product_id` exactly matches the storefront product;
2. methodology is present;
3. methodology status is exactly `accepted`;
4. `operator_review_required` is exactly `false`;
5. approval status is `APPROVED_FOR_LOCAL_PREVIEW`;
6. approval scope is `LOCAL_PREVIEW_ONLY`;
7. both authorization booleans are exactly `false`;
8. the SHA-256 matches the canonical copy.

Blocked, fallback, missing, or review-required methodology fails closed.

## 8. Public projection

Without the optional envelope, R112I1 behavior remains `IDENTITY_ONLY`.

With valid approval, `public_content` contains only the approved title,
description, facts, and proof, with
`content_state = "OPERATOR_APPROVED_LOCAL_COPY"`.

Approval metadata and the digest are not exposed in `public_content`.

## 9. Text validation

- product ID, title, and description must be non-empty strings;
- title maximum: 160 characters;
- description maximum: 2000 characters;
- facts and proof must be sequences, not strings;
- each sequence may contain at most 8 items;
- each item maximum: 400 characters;
- empty items fail closed;
- absolute HTTP, HTTPS, or FTP URLs fail closed.

## 10. Determinism and mutation

- input mappings are not mutated;
- output uses plain JSON-ready primitives;
- copy digest is deterministic;
- mapping key order does not affect custody;
- copy list order remains operator-controlled and digest-significant.

## 11. Test matrix

The executable matrix covers nominal approval, identity-only compatibility,
digest custody, mutation invalidation, product binding, exact keys,
authorization flags, methodology prerequisites, determinism, URL rejection,
mapping-order independence, internal-data non-projection, and forbidden
dependency scanning.

## 12. Non-goals

A8-R112I2 does not generate marketing copy, approve claims automatically,
inspect external evidence, render HTML/CSS/JavaScript, choose images, implement
cart or checkout, publish, spend, fulfill, or create external writes.
