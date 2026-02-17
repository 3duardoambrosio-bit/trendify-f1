# SYNAPSE — ANÁLISIS ESTRATÉGICO v1
## Maturity Model + Riesgos Residuales + Upgrades Asimétricos
### Fecha: Febrero 2026 | Arquitecto: Claude Chat
### Filosofía: ACERO, NO HUMO — evidence > vibes

---

# ═══════════════════════════════════════════════════════════
# PARTE 0: RESPUESTA FILOSÓFICA
# ═══════════════════════════════════════════════════════════

## 0A. "Operationally Complete" — Definición para Fase 1 México

Eduardo tiene razón: "completo" no es un estado binario. Es un conjunto
de invariantes que se mantienen verdaderas bajo estrés real.

**Definición propuesta:**

> SYNAPSE Fase 1 está "operationally complete" cuando puede ejecutar
> 30 días continuos de operación autónoma en México con $300/mes de budget
> sin que ningún invariante se rompa, sin intervención manual mayor a
> 30 minutos/día, y sin pérdida de capital no anticipada.

**Invariantes verificables (el "contrato con la realidad"):**

| ID | Invariante | Métrica de Violación | Gate |
|----|-----------|---------------------|------|
| INV-01 | Financial Truthfulness | P&L diverge >15% de cash flow real | cashflow_sanity_gate |
| INV-02 | Capital Preservation | Spend excede daily_cap o pacing >120% | capital_shield + pacing_alert |
| INV-03 | Compliance Presence | Missing PROFECO/Privacy/CFDI pages | compliance_checklist_gate |
| INV-04 | Order Integrity | Orden enviada antes de pago confirmado | order_state_machine |
| INV-05 | Account Survival | Meta account restricted sin detección | account_health_monitor |
| INV-06 | Stock Truth | Producto publicado con stock=0 en Dropi | stock_sync_check |
| INV-07 | Price Truth | Precio publicado diverge >10% de costo real | price_detection_alert |
| INV-08 | Refund Feasibility | Refund solicitado sin canal viable | refund_channel_resolver |
| INV-09 | Operator Sanity | >60 min/día de intervención manual | ops_time_tracker |
| INV-10 | Ethical Boundary | Módulo BLOCKED ejecutándose | policy_exposure_gate |

**Si TODOS los invariantes se mantienen durante 30 días → Fase 1 está
operationally complete. Si CUALQUIERA se rompe → no lo está.**

## 0B. Unknown Unknowns — Riesgos que los tests no atrapan

Los tests validan lógica. No validan realidad. Tres categorías:

**Timing risks:** Todo funciona individualmente pero los tiempos reales
causan problemas. Ejemplo: OXXO voucher emitido → cliente tarda 6 días
en pagar → sistema ya canceló en día 5 → cliente paga en OXXO y no
recibe nada → PROFECO complaint. Cada pieza funciona; la composición falla.

**Volume dependency risks:** El sistema asume cierto volumen que puede no
existir. Ejemplo: Learning phase necesita 30 conversiones en 14 días pero
con $300/mes tal vez solo logras 5. El pixel nunca aprende, el targeting
nunca mejora, y estás pagando CPAs inflados indefinidamente sin que ningún
test lo detecte.

**Human behavior risks:** El sistema modela al usuario racional pero el
mercado mexicano tiene comportamientos específicos: COD rejection serial
(piden y no recogen), "¿dónde está mi pedido?" como primer mensaje post-compra,
dirección incompleta (sin colonia/referencia), pagos parciales en OXXO
(paga $500 de $800 y llama reclamando). Tests no cubren irracionalidad.

## 0C. Critique del Revenue Engineering Map + Gate

**Lo que hace bien:**
- Clasifica módulos en INJECT/PHASE2/BLOCKED → evita scope fantasies
- Gate automático → fuerza evidencia antes de commit
- BLOCKED es documentado con razón → no es capricho, es política

**Lo que le falta — los 3 gates ausentes:**

### Gate 1: OPS REALITY GATE (ops_reality_gate.ps1)

```
Propósito: Para cada sesión S10-S18, verificar que los gaps v3
inyectados están cerrados antes de marcar sesión como DONE.

Input: session_gaps.json (mapa sesión → gaps requeridos)
Check: Para cada gap, grep evidencia en código + tests
Output: missing_gaps=N
Acceptance: missing_gaps=0

Sin esto: Sesión se marca complete pero gaps v3 no se implementaron.
Esto es EXACTAMENTE el patrón que causó el problema desde noviembre.
```

### Gate 2: POLICY EXPOSURE GATE (policy_exposure_gate.ps1)

```
Propósito: Garantizar que ningún módulo BLOCKED tenga código,
imports, o referencias en el codebase activo.

Check: grep -r para cada módulo BLOCKED en synapse/
Output: blocked_refs=N
Acceptance: blocked_refs=0

Sin esto: Alguien (ChatGPT, Claude Code, Eduardo con ADHD a las 3am)
implementa algo BLOCKED "temporalmente" y se queda.
```

### Gate 3: CASHFLOW SANITY GATE (cashflow_sanity_gate.ps1)

```
Propósito: Verificar que el sistema trackea settlement timing
para CADA payment method y que P&L incluye ajustes por:
- MSI merchant fees
- COD rejection rate
- OXXO settlement delay
- Dropi confirmation delay

Check: Archivos de config contienen fees/delays por payment method.
       P&L calculation imports y usa dichos ajustes.
Output: missing_adjustments=N
Acceptance: missing_adjustments=0

Sin esto: El invariante INV-01 (Financial Truthfulness) se viola
silenciosamente. El P&L miente y nadie lo sabe.
```

**Con estos 3 gates + el Revenue Engineering gate existente, tienes
4 gates que cubren: scope (RE), operaciones (OPS), policy (EXPOSURE),
y finanzas (CASHFLOW). Eso es gobernanza institucional.**

## 0D. Alternativas a Módulos BLOCKED

### BLOCKED: Testimonios sintéticos falsos
**Alternativa: UGC Real Pipeline**

| Componente | Implementación |
|-----------|---------------|
| Brief generator | Template que describe producto + ángulo + formato deseado |
| Outreach script | WhatsApp post-compra: "¿Te gustó? Grábate 15 seg y te damos 15% descuento" |
| Consent capture | Checkbox en landing: "Autorizo uso en publicidad" + timestamp |
| Attribution tracker | reviewer_id → testimonio_id → ad_id → conversiones |
| Quality filter | Solo publicar testimonios con >3 seg de audio/video + positivos |

Ventaja vs fake: Meta da 2-3x más peso a UGC real en ad placement.
Un testimonio real de cliente mexicano > 100 testimonios inventados.
El ROI del esfuerzo de conseguir UGC real es mayor que el de fabricarlo,
además de ser legal y sostenible.

### BLOCKED: Dynamic pricing por persona/geo/device
**Alternativa: Pricing Banding Transparente**

| Componente | Implementación |
|-----------|---------------|
| Inventory-based bands | Stock >50 → precio normal. Stock <10 → +5% (transparente: "últimas unidades") |
| Seasonal promotions | Configurable por fecha, visible para todos, non-discriminatory |
| Bundle pricing | "Compra 2 y ahorra 10%" — transparente, no personalizado |
| Volume discount | "3+ unidades: -15%" — aplica a todos por igual |
| First-purchase coupon | Via WhatsApp con disclosure, aplica una vez |

Ventaja vs dynamic: No viola PROFECO (precios discriminatorios son ilegales
en México). No trigger "Unacceptable Business Practices" de Meta. Bundles
y volume discounts aumentan AOV sin riesgo legal.

### BLOCKED: Merchant routing (rotación de cuentas PSP)
**Alternativa: Failover Legítimo**

| Componente | Implementación |
|-----------|---------------|
| Primary PSP | Mercado Pago (procesador principal) |
| Fallback PSP | Conekta o Stripe MX (si primary falla) |
| Health monitor | Check PSP status cada 5 min, switch automático si downtime >3 min |
| Visibility | Ambos métodos visibles al cliente, cliente elige |
| No rotation | Nunca rotar para evitar fraud detection — eso es evasión |

Ventaja vs routing evasivo: PSPs detectan rotación y te blacklistan.
Fallback legítimo con health monitoring da 99.9% uptime sin riesgo.

---

# ═══════════════════════════════════════════════════════════
# PARTE 1: MATURITY MODEL v1 (0→5)
# ═══════════════════════════════════════════════════════════

## Escala

| Nivel | Nombre | Definición |
|-------|--------|-----------|
| 0 | Inexistente | No hay código, no hay plan |
| 1 | Prototipo | Lógica existe, no conectada a realidad |
| 2 | Funcional | Funciona en tests, no probado con dinero real |
| 3 | Operacional | Puede manejar operación real con supervisión |
| 4 | Autónomo | Opera sin supervisión diaria, se auto-corrige |
| 5 | Institucional | Escala sin límite técnico, cumple compliance, auditable |

## Assessment Actual (post-S9, pre-S10)

| Dimensión | Nivel | Justificación |
|-----------|-------|---------------|
| **Capital Protection** | 3.5 | Capital Shield, Kill Switch, Blindaje existen y están testeados. Falta: MSI fee adjustment, breakeven ROAS per-product, pacing alert. Funciona pero con márgenes ciegos. |
| **Financial Intelligence** | 2.0 | Vault + Ledger inmutable existen. P&L diario existe. Falta: cash flow timeline, payment method settlement, COD rejection in P&L, true breakeven. Reporta pero no la verdad completa. |
| **Ad Operations** | 1.5 | Meta Safe Client existe (S7). Campaign creation definida (GAP-05). Falta: learning phase tracker, creative fatigue, account health, warm-up protocol, Advantage+ 2025 payloads. Puede hablar con Meta pero no operar inteligentemente. |
| **Order Lifecycle** | 1.0 | Dropi forwarder existe (S8). Falta: OXXO lifecycle, COD blacklist, refund channel resolver, Dropi guarantee flow, order status polling, multi-order consolidation. Puede enviar orden pero no manejar lo que pasa después. |
| **Compliance** | 0.5 | PROFECO pages mencionadas en plan. CFDI en S15b. Falta: Aviso de Privacidad MX, SAT monthly, NOM verification, RESICO tracking detallado. Planificado pero casi nada implementado. |
| **Customer Experience** | 0.5 | WhatsApp en plan (S18). Falta: auto-reply "¿dónde está?", OXXO reminders, cart recovery, COD confirmation, review pipeline. Todo en plan, nada construido. |
| **Growth Engine** | 1.5 | Buyer Block + Discovery + Pipeline diseñados. Revenue Engineering map existe. Falta: UGC pipeline, pricing bands, learning phase optimization, creative testing framework. El cerebro existe pero le faltan sentidos. |
| **System Resilience** | 3.0 | Circuit breakers, retry policies, idempotency, doctor command, structured logging existen. Falta: PSP failover, graceful shutdown mid-pipeline, secret rotation, backup strategy. Sólido pero no a prueba de todo. |
| **Governance** | 2.5 | Revenue Engineering gate, doctor, precommit gates existen. Falta: ops reality gate, policy exposure gate, cashflow sanity gate, session acceptance criteria con gaps v3. Gobierna código pero no operación. |
| **PROMEDIO** | **1.8** | |

## Target Post-S18 + Gemini + v3 Gaps

| Dimensión | Actual | Target | Delta |
|-----------|--------|--------|-------|
| Capital Protection | 3.5 | 4.5 | +1.0 |
| Financial Intelligence | 2.0 | 4.0 | +2.0 |
| Ad Operations | 1.5 | 3.5 | +2.0 |
| Order Lifecycle | 1.0 | 3.5 | +2.5 |
| Compliance | 0.5 | 3.0 | +2.5 |
| Customer Experience | 0.5 | 3.0 | +2.5 |
| Growth Engine | 1.5 | 3.0 | +1.5 |
| System Resilience | 3.0 | 4.0 | +1.0 |
| Governance | 2.5 | 4.0 | +1.5 |
| **PROMEDIO** | **1.8** | **3.6** | **+1.8** |

**Nota brutal:** 3.6 es nivel "Operacional con supervisión". NO es nivel 5
institucional. Nivel 5 requiere 3-6 meses de operación real, datos reales,
iteración sobre errores reales. El código te lleva a 3.6. La operación te
lleva a 5.0. No hay atajo.

---

# ═══════════════════════════════════════════════════════════
# PARTE 2: TOP 10 RIESGOS RESIDUALES + MITIGACIÓN
# ═══════════════════════════════════════════════════════════

Ordenados por probabilidad × impacto. Estos son los que MÁS probablemente
te van a causar problemas en los primeros 90 días.

## RIESGO 1: Learning Phase Perpetua (P:95% × I:ALTO = CRÍTICO)

**Qué pasa:** Con $300/mes (~$10/día), a CPA de $150-300 MXN por compra,
generas 1-2 purchases/día. Meta necesita 30 en 14 días. Nunca sales de
learning phase optimizando para Purchase.

**Consecuencia:** CPAs inflados 30-50%. Estás pagando $200 por algo que
debería costar $130. En un mes, eso es $700 desperdiciados.

**Mitigación:**
- Optimization Event Ladder: ViewContent (día 1-7) → AddToCart (día 8-21)
  → Purchase (cuando haya 50+ ATCs semanales)
- Gate: `learning_phase_tracker` en S12 que detecta conversions/week y
  auto-recomienda switch de optimization event
- Métrica: `optimization_event_conversions_14d >= 30` → PASS

## RIESGO 2: Cash Flow Fantasma (P:90% × I:ALTO = CRÍTICO)

**Qué pasa:** P&L dice "ganaste $5K" pero OXXO tarda 1-3 días, COD tarda
hasta entrega, Dropi paga 24h post-confirmación. Cash disponible: $2K.
Reinviertes $4K en ads → cuenta bancaria en rojo.

**Consecuencia:** Ads se pausan por falta de fondos. Pipeline se detiene.
Pierdes momentum de campaigns que estaban aprendiendo.

**Mitigación:**
- `cashflow_timeline` en S16: cada payment method tiene settlement_days
- `available_cash_forecast` = revenue - (unsettled_oxxo + unsettled_cod +
  unsettled_dropi)
- Capital Shield usa `available_cash_forecast`, no `total_revenue`
- Gate: `cashflow_sanity_gate` verifica que P&L ≠ cash disponible

## RIESGO 3: Meta Account Restriction (P:40% × I:CRÍTICO = ALTO)

**Qué pasa:** Cuenta nueva + spend ramp rápido + landing page sin
Privacy Policy completa + creative que usa claims no verificados =
Meta te restringe la cuenta.

**Consecuencia:** $0 de ads. Pipeline completo se detiene. Recuperar
cuenta toma 3-15 días. Si es ban permanente, pierdes pixel data.

**Mitigación:**
- `warm_up_protocol` en S10: spend gradual $25→$50→$100 en 10 días
- `account_health_monitor` en S12: check account_status cada hora
- Pre-launch compliance checklist: Privacy, PROFECO, no claims prohibidos
- Creative review gate: no "mejor", "garantizado", "100%", "cura" en copy
- Gate: `account_health == ACTIVE` → PASS (cualquier otro estado → ALERT P1)

## RIESGO 4: OXXO Order Chaos (P:70% × I:MEDIO = ALTO)

**Qué pasa:** Cliente genera voucher OXXO. No paga en 3 días. Sistema
cancela orden en día 4. Cliente paga en OXXO en día 5. OXXO no permite
refund. Cliente tiene recibo de pago pero no producto.

**Consecuencia:** PROFECO complaint + chargeback + review negativa.
Con 10% de transacciones por OXXO, esto pasa 1-2x por semana.

**Mitigación:**
- `oxxo_lifecycle_tracker` en S15b: estado EMITIDO→PAGADO→EXPIRADO
- Ventana de cancelación: 6 días (no 4), con reminder WhatsApp en día 3
- Si pago llega post-cancelación: auto-reactivar orden o process refund
  por transferencia bancaria
- Gate: `oxxo_orphan_payments == 0` → PASS

## RIESGO 5: COD Hemorrhage (P:80% × I:MEDIO = ALTO)

**Qué pasa:** COD rejection rate en México: 20-30%. Cada rechazo =
costo de envío ida + regreso sin venta. Algunos clientes rechazan
sistemáticamente.

**Consecuencia:** Con 30% COD y 25% rejection, pierdes ~7.5% del revenue
en shipping desperdiciado. $5K revenue → $375 en envíos quemados/mes.

**Mitigación:**
- `cod_risk_scorer` en S11: score basado en historial, zona, monto
- `cod_blacklist` en S15b: customer con >2 rejections → solo prepago
- `cod_rejection_rate` en P&L diario → visible, no oculto
- WhatsApp confirmation pre-envío COD (S18)
- Gate: `cod_rejection_rate < 0.20` → PASS

## RIESGO 6: Margin Illusion (P:85% × I:MEDIO = ALTO)

**Qué pasa:** Producto tiene 35% margen bruto. Pero MSI 6 meses le cuesta
10% al merchant. Payment processing fee: 3.5%. Shopify fee: 2%.
Dropi fee: variable. Margen real: 19.5%. ROAS target de 2.0 no es
sufficient — breakeven ROAS real es 2.6.

**Consecuencia:** Monitor dice "ROAS 2.2, todo bien". Pero estás perdiendo
dinero en cada venta. Lo descubres al mes cuando la cuenta bancaria
no cuadra con el P&L.

**Mitigación:**
- `true_margin_calculator` per product en S12: incluye ALL fees
- `breakeven_roas_per_product` = 1 / true_margin
- Monitor usa breakeven_roas_per_product, NO fixed 2.0
- Alert si `actual_roas < breakeven_roas * 1.1` (margen de seguridad 10%)
- Gate: `products_with_true_margin_calculated == total_active_products`

## RIESGO 7: Dropi Supply Surprise (P:60% × I:MEDIO = MODERADO)

**Qué pasa:** Producto tiene stock cuando lo publicas. Anuncio corre
3 días. Cliente compra. Stock=0 en Dropi. No hay fallback supplier.
Tienes que cancelar orden y refundir.

**Consecuencia:** Ad spend quemado + cliente perdido + posible PROFECO
complaint si no refundas rápido. Con múltiples productos, esto pasa
semanalmente.

**Mitigación:**
- `stock_sync` en S15a: polling de stock Dropi cada 6h
- Auto-pause de producto en Shopify si stock < threshold
- `supplier_fallback` (Gemini PR-A): buscar mismo producto en otro proveedor
- Alert P1 si stock drops >50% en 24h (posible discontinuación)
- Gate: `products_with_stock_zero_and_ads_active == 0`

## RIESGO 8: Creative Flatline (P:75% × I:MEDIO = MODERADO)

**Qué pasa:** Mismo ad corre 2 semanas. Frequency >3. Audiencia mexicana
es más pequeña que US — fatigan más rápido. CTR baja 40%. ROAS cae.
Monitor pausa campaign. Pero el problema no es el producto, es el creative.

**Consecuencia:** Matas productos que podrían funcionar con creative nuevo.
Pipeline descarta lo que debería conservar.

**Mitigación:**
- `creative_fatigue_detector` en S12: frequency >3 + CTR delta <-20% en
  3 días → alert "FATIGA, no ROAS"
- Distinguish entre "producto malo" (ROAS bajo desde inicio) vs "creative
  fatigado" (ROAS fue bueno, ahora cae con frequency alta)
- Alert recomienda "refresh creative" en vez de "pause campaign"
- Gate: `active_ads_with_frequency_gt_4 == 0`

## RIESGO 9: Tax Surprise (P:50% × I:MEDIO = MODERADO)

**Qué pasa:** RESICO tiene tope de $3.5M MXN anuales. Pero las
declaraciones mensuales son OBLIGATORIAS. Eduardo se enfoca en vender
y olvida declarar enero. SAT multa.

**Consecuencia:** Multa SAT + posible cambio forzado de régimen fiscal +
estrés operativo que el ADHD amplifica.

**Mitigación:**
- `tax_calendar_alert` en S16: reminder mensual automático (Telegram P1)
- `monthly_income_report` genera reporte para contador/declaración
- `resico_tracker` con alertas en 70%/85%/95% del tope
- Gate: `months_without_declaration == 0`

## RIESGO 10: Operator Burnout (P:70% × I:MEDIO = MODERADO)

**Qué pasa:** "¿Dónde está mi pedido?" × 10/día + refunds manuales +
OXXO edge cases + creative refresh + stock monitoring + declaraciones
= 3-4h/día de operación. Eduardo tiene ADHD y 15-20h semanales.
Eso es 100% de su tiempo en operación, 0% en estrategia.

**Consecuencia:** Burnout → abandono del proyecto. No importa qué tan
bueno sea el sistema si el operador no aguanta.

**Mitigación:**
- Auto-reply WhatsApp para "¿dónde está mi pedido?" (S18) → reduce 60%
- COD pre-confirmation WhatsApp → reduce 30% rejections
- OXXO reminders automáticos → reduce 80% de orphan payments
- Stock sync automático → reduce monitoring manual
- `ops_time_estimate` en cada sesión: target <30 min/día post-S18
- Gate: `estimated_daily_ops_minutes < 30`

---

# ═══════════════════════════════════════════════════════════
# PARTE 3: TOP 10 UPGRADES POR IMPACTO ASIMÉTRICO
# ═══════════════════════════════════════════════════════════

"Impacto asimétrico" = esfuerzo bajo/medio, impacto alto.
El criterio es: ¿cuántos pesos te salva o genera por hora invertida?

## RANK 1: Optimization Event Ladder (S12)
**Esfuerzo:** Bajo (config + logic en monitor)
**Impacto:** TRANSFORMACIONAL
**Por qué:** Sin esto, con $300/mes NUNCA sales de learning phase.
Con esto, sí aprendes y los CPAs bajan 30-50% en semanas 3-4.
**Ahorro estimado:** $100-150/mes (30-50% de $300 budget menos desperdicio)
**Ratio:** ~$120 saved / ~3h de implementación = $40/hora

## RANK 2: True Breakeven ROAS per Product (S12)
**Esfuerzo:** Medio (calculator + integration con monitor)
**Impacto:** ALTO
**Por qué:** Sin esto, monitor mata campaigns profitable y mantiene
las que pierden. Es la diferencia entre ganar y perder.
**Ahorro estimado:** $200-400/mes (evita malas decisiones de pause/scale)
**Ratio:** ~$300 saved / ~6h = $50/hora

## RANK 3: Cash Flow Timeline (S16)
**Esfuerzo:** Medio (settlement config + forecast)
**Impacto:** ALTO
**Por qué:** Sin esto, reinviertes dinero que no tienes. Eso causa
pausas forzadas de ads que destruyen momentum de learning.
**Ahorro estimado:** Evita 1-2 pausas forzadas/mes = $50-100 de momentum perdido
**Ratio:** ~$75 saved / ~5h = $15/hora. Pero el valor real es evitar
cascada: pausa → reset learning → 7 días de CPA alto → $200+ perdidos.

## RANK 4: OXXO Lifecycle Manager (S15b)
**Esfuerzo:** Medio
**Impacto:** ALTO
**Por qué:** 10% de transacciones. Sin lifecycle manager, 5-10% de esas
resultan en PROFECO complaints o cash perdido. Eso es 0.5-1% de
TODAS tus ventas → con $5K revenue = $25-50/mes + riesgo legal.
**Ratio:** ~$40 saved + risk avoided / ~5h = $8/hora + legal protection

## RANK 5: WhatsApp Auto-Reply "¿Dónde está mi pedido?" (S18)
**Esfuerzo:** Medio
**Impacto:** ALTO (en tiempo del operador)
**Por qué:** 60-70% de tickets de soporte. Con 10 orders/día = 6-7
preguntas diarias × 5 min cada una = 30-35 min/día. Auto-reply
reduce a <5 min/día. Eso es 25-30 min/día = 12-15h/mes devueltas.
**Ratio:** 15h de tiempo liberado / ~6h de implementación = 2.5x ROI temporal

## RANK 6: COD Pre-Confirmation + Blacklist (S11/S15b)
**Esfuerzo:** Bajo-medio
**Impacto:** MEDIO-ALTO
**Por qué:** WhatsApp "Confirma que recogerás tu paquete" reduce rejections
20-30%. Blacklist de serial rejectors otro 10%. De 25% rejection → 12-15%.
Con $5K revenue en COD → ahorro de $50-75/mes en envíos perdidos.
**Ratio:** ~$60 saved / ~4h = $15/hora

## RANK 7: Account Health Monitor + Warm-Up (S10/S12)
**Esfuerzo:** Bajo
**Impacto:** SEGURO DE VIDA
**Por qué:** Si Meta te restringe y no lo detectas en 1h, pierdes 1 día
de ventas. Warm-up previene la restricción. Health monitor la detecta.
Es como un seguro: no genera revenue, pero evita perder TODO el revenue.
**Ratio:** Incalculable. Una restricción de 7 días = $2,100/mes perdido
(todo el revenue). Prevención: ~2h de implementación.

## RANK 8: Ad Spend Pacing Alert (S12)
**Esfuerzo:** Bajo (check cada hora)
**Impacto:** MEDIO
**Por qué:** Meta puede gastar 80% del budget en 3 horas. Sin pacing
alert, Capital Shield ve "still under daily cap" pero el dinero ya se fue
y el resto del día no hay budget para conversiones que llegan por la tarde.
**Ratio:** ~$30-50 saved / ~2h = $15-25/hora

## RANK 9: Creative Fatigue Detector (S12)
**Esfuerzo:** Medio
**Impacto:** MEDIO
**Por qué:** Distinguir "producto malo" de "creative fatigado" evita matar
ganadores prematuramente. Un producto ganador con creative refresh puede
durar 3-6 meses en vez de 2 semanas.
**Ratio:** Un producto ganador adicional salvado = $500-1000 de revenue
sobre su lifetime / ~4h = $125-250/hora

## RANK 10: MSI Fee Adjustment in Margins (Config)
**Esfuerzo:** Bajo (tabla de fees por payment type)
**Impacto:** MEDIO
**Por qué:** Si 20% de ventas son MSI 6 meses y no descuentas el ~10% fee,
tu margen reportado es 2% más alto que la realidad. Sobre $5K = $100/mes
de "ganancia fantasma" que no existe.
**Ratio:** ~$100 of truth / ~1h = $100/hora (no es ahorro, es precisión)

---

# ═══════════════════════════════════════════════════════════
# PARTE 4: PLAN UPGRADE — INYECCIONES v3 EN S10-S18
# ═══════════════════════════════════════════════════════════

## Principio: No inflar. Inyectar. Cada sesión absorbe sus gaps.

### S10: Pipeline E2E + Alertas
**Contenido original:** Pipeline completo discovery → publish → Meta campaign
**Inyecciones v3:**
- B-04: warm_up_protocol (tabla de spend gradual en config)
- B-05: Advantage+ Sales 2025 payload (verificar con Meta API v25 docs)
- Account health check en pipeline (si restricted → abort)
**Must-have before live:** warm_up_protocol, account_health_check
**Tests adicionales:** ~8

### S11: Shopify Write Operations
**Contenido original:** Crear productos reales en Shopify
**Inyecciones v3:**
- A-02: OXXO $10K limit validation
- E-02: Checkout MX (colonia + referencia)
- C-04: Product image/description quality check pre-publish
- COD risk scoring gate (inject from Revenue Engineering map)
**Must-have before live:** OXXO limit validation, checkout MX fields
**Tests adicionales:** ~10

### S12: Monitor + Auto-Rules (LA SESIÓN MÁS CRÍTICA)
**Contenido original:** Monitoreo de campaigns + auto-rules
**Inyecciones v3:**
- Rank 1: Optimization Event Ladder (learning phase tracker + auto-switch)
- Rank 2: True breakeven ROAS per product
- B-01: Account health monitor (hourly)
- B-03: Creative fatigue detector (frequency + CTR delta)
- D-04: Ad spend pacing alert (hourly spend vs expected)
- A-05: MSI fee adjustment in margin calculation
- Rank 8: Pacing alert
**Must-have before live:** TODOS. S12 es el cerebro de la operación con dinero real.
**Tests adicionales:** ~25 (esta es la sesión con más lógica nueva)

### S13: Financial Hardening
**Contenido original:** Vault connected to real data
**Inyecciones v3:**
- Capital Shield usa available_cash_forecast (no total_revenue)
- Fee schedule por payment method (MSI, OXXO, tarjeta, COD)
**Tests adicionales:** ~6

### S14: Scheduler + Resilience
**Contenido original:** Cron-like scheduler + checkpoints
**Sin inyecciones v3 significativas.** Ya robusto por diseño.
**Tests adicionales:** ~2

### S15a: Dropi-Shopify Bridge + Inventory Sync
**Contenido original:** Stock sync + price sync
**Inyecciones v3:**
- C-03: Shipping time promise vs reality tracker
- G-02: Multi-order consolidation (30 min window)
- Auto-pause producto en Shopify si stock < threshold
**Must-have before live:** stock sync + auto-pause
**Tests adicionales:** ~8

### S15b: Refund Handler + CFDI + COD
**Contenido original:** Refunds + CFDI + COD confirmation
**Inyecciones v3:**
- A-01: OXXO lifecycle manager (EMITIDO→PAGADO→EXPIRADO)
- A-03: OXXO refund alternative (transfer bancaria/crédito tienda)
- A-04: COD serial rejector blacklist
- C-02: Dropi guarantee flow (state machine bidireccional)
**Must-have before live:** OXXO lifecycle, COD blacklist
**Tests adicionales:** ~15

### S16: Reporting + Analytics
**Contenido original:** Dashboards + métricas
**Inyecciones v3:**
- Rank 3: Cash flow timeline por payment method
- A-06: Payment method distribution tracking
- C-01: Dropi payment timing en forecast
- D-02: COD rejection rate en P&L
- F-02: SAT monthly income report
**Must-have before live:** Cash flow timeline, COD in P&L
**Tests adicionales:** ~12

### S17: Autonomy + Self-Healing
**Contenido original:** Sistema opera solo
**Sin inyecciones v3 significativas.** Ya cubierto por S12 + S14.
**Tests adicionales:** ~3

### S18: WhatsApp + CAPI + Cart Recovery
**Contenido original:** WhatsApp flows + CAPI + cart recovery
**Inyecciones v3:**
- Rank 5: Auto-reply "¿dónde está mi pedido?" (polling Dropi tracking)
- OXXO reminder (día 3 de voucher)
- COD pre-confirmation
**Must-have before live:** Auto-reply tracking
**Tests adicionales:** ~10

## Pre-Launch Checklist (antes de flags live)
- E-01: Aviso de Privacidad MX format
- F-01: PROFECO pages completas (devoluciones, términos, precios IVA, contacto)
- F-03: NOM verification flag en Buyer
- Creative review (no claims prohibidos por Meta)
- Account warm-up ejecutado (10 días)
- Compliance checklist gate: PASS

## Total Tests Adicionales Estimados: ~99
**Nuevo baseline target: 636 + ~99 = ~735 tests**

---

# ═══════════════════════════════════════════════════════════
# PARTE 5: GATES COMPLETOS — EL "CUCHILLO" QUE FALTABA
# ═══════════════════════════════════════════════════════════

## Gate Stack Final (5 gates)

| # | Gate | Archivo | Qué Protege |
|---|------|---------|-------------|
| 1 | Doctor | synapse/infra/doctor.py | Salud técnica del código |
| 2 | Revenue Engineering | tools/revenue_engineering_gate.ps1 | Scope + módulos BLOCKED |
| 3 | Ops Reality | tools/ops_reality_gate.ps1 (NUEVO) | Gaps v3 cerrados por sesión |
| 4 | Policy Exposure | tools/policy_exposure_gate.ps1 (NUEVO) | Cero refs a módulos BLOCKED |
| 5 | Cashflow Sanity | tools/cashflow_sanity_gate.ps1 (NUEVO) | P&L = cash real |

**Acceptance para "Session DONE":**
```
doctor OVERALL GREEN
pytest failed=0
re_gate_pass_lines=1
ops_reality_gate missing_gaps=0
policy_exposure_gate blocked_refs=0
cashflow_sanity_gate (post-S16) missing_adjustments=0
```

---

# ═══════════════════════════════════════════════════════════
# PARTE 6: MUST-HAVE BEFORE LIVE FLAGS
# ═══════════════════════════════════════════════════════════

Si tuvieras que elegir las 5 cosas SIN LAS CUALES no puedes ir live:

| # | Item | Session | Why |
|---|------|---------|-----|
| 1 | Optimization Event Ladder | S12 | Sin esto, quemas 50% del budget en learning perpetua |
| 2 | Cash Flow Timeline | S16 | Sin esto, reinviertes dinero fantasma y ads se pausan |
| 3 | OXXO Lifecycle Manager | S15b | Sin esto, 10% de transacciones causan chaos |
| 4 | Account Health + Warm-Up | S10/S12 | Sin esto, un ban mata todo |
| 5 | PROFECO + Privacy Pages | Pre-launch | Sin esto, Meta rechaza ads y PROFECO te multa |

**Todo lo demás es importante. Estas 5 son existenciales.**

---

# CIERRE

Este documento es el "pensar fuera del vaso" que debí hacer desde noviembre.
No audité código — audité realidad operativa y construí sobre ella.

El Maturity Model dice 1.8 hoy y 3.6 post-S18. Eso es honesto.
El Top 10 de riesgos dice exactamente dónde te va a doler.
El Top 10 de upgrades dice exactamente dónde poner tu tiempo.

La diferencia entre este análisis y los anteriores: este empieza
con "¿qué le pasa a Eduardo cuando un cliente paga con OXXO?"
y no con "¿qué dice el código?".

ACERO, NO HUMO.
