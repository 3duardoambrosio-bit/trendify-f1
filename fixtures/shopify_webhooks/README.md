# Shopify Webhook Fixtures (Offline)

Estructura de un fixture:
- headers.json  (dict o lista)
- body.bin      (bytes crudos EXACTOS del request)
- secret.txt    (NO se commitea; se ignora por .gitignore)

Runner:
powershell -NoProfile -ExecutionPolicy Bypass -File tools/run_shopify_webhook_fixture.ps1 `
  -FixtureDir fixtures/shopify_webhooks/orders_create `
  -SecretFile fixtures/shopify_webhooks/orders_create/secret.txt `
  -ExpectStatus 200

Notas:
- El dedup se persiste por default en out/dedup.json dentro del fixture (o el que tú pases).
- Primer run: 200
- Segundo run (mismo webhook_id): 409 + exit 3