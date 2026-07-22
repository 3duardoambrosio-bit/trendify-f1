# A8-R112I1 — Storefront Read Model Contract

## 1. Purpose

A8-R112I1 defines the first dedicated storefront boundary in SYNAPSE.

It converts validated, operator-controlled local catalog state into a
deterministic JSON-ready model for a **local preview only**. It does not render
HTML yet and does not connect to Shopify, Dropi, Meta, checkout, publication,
spend, or fulfillment.

## 2. Source-of-truth correction

A8-R111 enriches `fixture.decision.methodology` with the sealed methodology
decision, but it does **not** persist the original explicit
`methodology_context` inside the fixture.

Therefore, the R112I1 input is not a bare enriched fixture. Each input item must
bind both objects explicitly:

```python
{
    "fixture": <A8-R110 fixture optionally enriched by A8-R111>,
    "methodology_context": <exact explicit A8-R111 operator context>,
}
```

This prevents R112 from guessing product facts, proof, buyer state, claim risk,
channel, margin profile, or category.

## 3. Public API

```python
build_storefront_read_model(
    items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]

serialize_storefront_read_model(
    model: Mapping[str, Any],
) -> str
```

The builder is pure and non-mutating. The serializer emits canonical UTF-8
JSON text using sorted keys, compact separators, no NaN/Infinity, and one final
newline.

## 4. Required item fields

Each item contains exactly:

- `fixture`
- `methodology_context`

Unknown item fields fail closed.

### 4.1 Fixture requirements

- `source_kind == "operator_local_catalog_import"`
- `product.product_id`: non-empty string
- `product.name`: non-empty string
- `product.category`: non-empty string
- `product.supplier`: non-empty string, operator-only
- `product.market == "MX"`
- `decision.outcome`: non-empty string
- `decision.permission_gate == "REVIEW"`

`decision.methodology` may be absent. Its absence is represented honestly in
the preview status.

### 4.2 Methodology-context requirements

The context follows the A8-R111 exact field contract:

- `product_facts`
- `product_id`
- `buyer_state`
- `proof_available`
- `claim_risk`
- `channel`
- `margin_profile`
- `category`
- optional `candidate_output`

Unknown context fields fail closed.

`methodology_context.product_id` and `.category` must exactly match the fixture.

Absolute web URLs are forbidden in context sequences at this boundary because
R112I1 produces an offline preview and does not establish a media-evidence
policy.

## 5. Output schema

```json
{
  "schema_version": "a8-r112.storefront_read_model.v1",
  "mode": "LOCAL_PREVIEW",
  "currency": "MXN",
  "safety": {
    "checkout_enabled": false,
    "publication_enabled": false,
    "external_writes_enabled": false,
    "fulfillment_enabled": false,
    "spend_enabled": false
  },
  "home": {
    "featured_product_ids": [],
    "routes": {"home": "/"}
  },
  "collections": [],
  "products": []
}
```

### 5.1 Product projection

The public projection contains:

- identity: `product_id`, `slug`, `title`, `category`, `market`
- honest preview state
- canonical display price when explicit
- local relative routes
- identity-only public content

The operator projection contains only bounded status metadata:

- permission gate
- decision outcome
- methodology presence/status
- methodology review requirement
- counts of product facts and proof records

It does not expose the context values themselves.

## 6. Preview statuses

- `READY`: explicit price and methodology decision are present
- `PRICE_MISSING`: methodology exists, explicit price does not
- `METHODOLOGY_MISSING`: explicit price exists, methodology does not
- `PRICE_AND_METHODOLOGY_MISSING`: both are absent

Only `READY` products appear in `home.featured_product_ids`.

`READY` means ready for local preview, not ready for publication.

## 7. Money contract

R112I1 does not recalculate financial evaluation.

It reads only explicit `economics.price_mxn` and requires:

- `economics.currency == "MXN"`
- finite decimal
- amount greater than zero

The output amount is a canonical two-decimal string using `ROUND_HALF_UP`.

No `float`, `Decimal`, enum, supplier cost, shipping cost, contribution margin,
risk flag, or financial decision object reaches the public model.

## 8. Content boundary

A8-R111 methodology `safe_output` is not publication authorization.

R112I1 therefore does not transform or expose:

- `safe_output`
- product facts
- proof text
- supplier identity
- buyer state
- claim risk
- channel
- margin profile
- candidate output
- internal financial fields

`public_content` remains identity-only with empty description, facts, and proof.
A later operator-controlled island must define and approve customer-facing copy.

## 9. Determinism

- input is never mutated
- products sort by `product_id`
- collections sort by collection slug
- collection membership sorts by `product_id`
- product and collection routes are relative and deterministic
- duplicate product IDs fail closed
- duplicate product slugs fail closed
- collection slug collisions fail closed
- identical input produces identical model and canonical JSON text

## 10. Safety invariants

Always false:

- checkout
- publication
- external writes
- fulfillment
- spend

Forbidden dependencies include network, subprocess, Shopify, Dropi, and Meta
clients.

## 11. Test matrix

The executable matrix covers:

1. nominal ready preview
2. safety envelope
3. missing price
4. missing methodology
5. both missing
6. wrong source kind
7. non-REVIEW gate
8. product/category context mismatch
9. unknown item/context fields
10. duplicate product ID
11. duplicate product slug
12. zero, negative, non-finite, boolean, and null prices
13. canonical money rounding
14. public-data non-leakage
15. bounded operator metadata
16. non-mutation and determinism
17. deterministic product/collection order
18. safe empty preview
19. pure JSON output
20. absolute-URL rejection
21. forbidden dependency scan

## 12. Non-goals

A8-R112I1 does not:

- generate HTML/CSS/JavaScript
- establish a visual theme
- create product descriptions or claims
- select images
- implement cart or checkout
- publish to Shopify
- call Dropi or Meta
- authorize spend
- authorize fulfillment
- create external writes
