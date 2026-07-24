# A8-R113 — Canonical Product Bridge Contract

## 1. Objetivo

A8-R113 conecta el discovery sintético, la evaluación financiera,
la metodología comercial, la aprobación de customer copy y el
storefront local mediante una sola identidad de producto.

```text
DiscoveryCandidate.candidate_id
==
promoted fixture.product.product_id
==
methodology_context.product_id
==
customer_copy.product_id
==
storefront product_id
```

La identidad nominal controlada es:

```text
disc_71c892da6f966e
```

## 2. Fuente honesta

El bridge emite exclusivamente:

```text
source_kind=operator_approved_discovery_promotion
```

No puede declarar `operator_local_catalog_import`, porque la fuente
es un candidato sintético promovido explícitamente por el operador
y no un catálogo CSV local.

La promoción no constituye:

- evidencia live de mercado;
- inventario confirmado;
- disponibilidad confirmada del proveedor;
- autorización de publicación;
- autorización de gasto;
- autorización de fulfillment.

## 3. Aprobación de promoción

La aprobación se vincula de forma exacta con:

- `candidate_id`;
- SHA-256 del snapshot canónico completo;
- `decision_run_id`;
- decisión financiera;
- decisión final;
- operador;
- registro de aprobación.

Los siguientes campos deben ser exactamente `false`:

```text
publication_authorized
external_writes_authorized
spend_authorized
fulfillment_authorized
```

Valores equivalentes como `0`, `null`, `"false"` o `true` se
rechazan mediante validación fail-closed.

## 4. Custodia canónica

El fixture promovido incluye el envelope `canonical_bridge` con:

- versión de esquema;
- source kind;
- identidad canónica;
- snapshot completo del candidato;
- campo canónico `candidate_snapshot`;
- SHA-256 del snapshot;
- aprobación del operador;
- decisión vinculada.

Metodología y storefront recalculan el digest y verifican la
identidad antes de aceptar un fixture promovido.

Una mutación del snapshot, producto, decisión, digest o aprobación
debe fallar cerrada.

La custodia también vincula la economía visible con el snapshot canónico:

```text
economics.currency == MXN
economics.price_mxn == candidate_snapshot.price
economics.landed_cost_mxn == candidate_snapshot.cost
```

Las comparaciones de precio y costo usan equivalencia decimal finita.
Una moneda distinta, un valor no finito o cualquier discrepancia
debe fallar cerrada antes de metodología o storefront.

## 5. Metodología

El contexto metodológico permanece explícito y separado de la
aprobación de promoción.

El bridge no inventa ni autoriza automáticamente:

- product facts;
- proof;
- buyer state;
- claim risk;
- channel;
- margin profile;
- customer copy.

El `permission_gate` permanece en `REVIEW`.

## 6. Customer copy

El `safe_output` metodológico no se convierte automáticamente en
contenido público.

Customer copy requiere una aprobación independiente, otro SHA-256
y el mismo `product_id` canónico.

La salida pública no expone:

- digest de custodia;
- operador o approval record;
- decision run;
- safe output metodológico;
- buyer state o claim risk;
- landed cost, CAC o contribution margin.

## 7. Storefront local

El storefront puede emitir exclusivamente un preview local con:

```text
preview_status=READY
publication_status=NOT_AUTHORIZED
content_state=OPERATOR_APPROVED_LOCAL_COPY
```

Esto no constituye publicación ni autorización live.

## 8. Safety envelope

A8-R113 no introduce:

- llamadas de red;
- Shopify live;
- Dropi live;
- Meta live;
- checkout;
- publicación;
- external writes;
- gasto real;
- fulfillment.

Todos los indicadores de seguridad del storefront permanecen en
`false`.

## 9. Fixtures nominales

La isla contiene tres fixtures deterministas:

- `nominal_promotion_approval.json`;
- `nominal_methodology_context.json`;
- `nominal_customer_copy_approval.json`.

Los tres preservan la identidad `disc_71c892da6f966e` y no
autorizan publicación, writes, gasto ni fulfillment.
