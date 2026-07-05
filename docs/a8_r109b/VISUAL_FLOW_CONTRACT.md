# A8-R109B — Operator Workbench Visual Flow Contract (I1B)

## 1. Scope

A8-R109B-I1B adds the first tracked professional visual flow layer on top of
the frozen R109A/R109A.1 contract:

```
frozen fixtures (tests/fixtures/a8_r109a/)
  -> deterministic ViewModel (synapse/ui/operator_workbench_view_model.py, v3)
  -> R109A audit renderer (synapse/ui/operator_workbench_renderer.py)   [unchanged]
  -> R109B visual flow renderer (synapse/ui/operator_workbench_visual.py)  [new]
  -> tests (tests/ui/test_a8_r109b_operator_workbench_visual.py)
```

The visual renderer is a pure function `ViewModel -> HTML string`. One
self-contained file per fixture, openable via the file protocol. No server,
no Streamlit, no network, no credentials, no live writes, no spend, no
fulfillment, no analytics, no PMF claims.

## 2. What it consumes (no renderer inference)

The visual layer reads the R109A.1 system surfaces directly:

| Contract surface | Used for |
|---|---|
| `module_status_summary` | Module rail entries, badges, per-module status attributes |
| `candidate_pipeline` | Command Center pipeline card (fixture-only, honesty note visible) |
| `blocked_queue_summary` | Blocked Queue module + suppression of prepare CTA |
| `action_queue` | Command Center action list; the single `is_primary` action drives the header CTA |
| `system_health_board` | Command Center system state card |
| `capability_surface_map` | Evidence module honesty tiers (real_now / fixture_only / future / forbidden) |
| `copy_payloads` | Copy buttons (byte-exact canonical payloads, never re-assembled in the renderer) |
| Marketing Pack V2 fields | Marketing Engine tabs (angle_matrix, creative_hypotheses, claim_risk_by_copy, input_support_map, confidence_by_section, testing_plan_with_thresholds) |

Statuses and badges come from the contract. The renderer never derives
"blocked" or "ready" from strings.

## 3. Layout

Left module rail (10 modules from `module_status_summary`, fixed order):
Command Center, Decision Center, Product Lab, Economics, Shopify Studio,
Marketing Engine, Safety / Claim Guard, Evidence, Learning / Feedback,
Blocked Queue. Sticky command header: product identity, decision status,
margin/breakeven, and the primary action CTA. One module visible at a time.

Marketing Engine is a workspace with tabs: Estrategia, Angulos, Hook Bank,
Ad Copy, Canales/Scripts, Plan de Pruebas, Learning. Claim Guard cards are
adjacent to the Shopify payloads and the Ad Copy tab (`data-adjacent-to`).
Claim risk notes (`claim_risk_by_copy`) render inline under each copy surface.

## 4. State rules

| Fixture | Behavior |
|---|---|
| `recommended` | Selling-prep flow; header CTA `data-cta="prepare"`; copy buttons active |
| `blocked` | Blocked Queue opens first; `data-cta="prepare"` never rendered; copy buttons suppressed in Shopify Studio and Marketing Engine (`data-copy-suppressed`); blocked banners dominate |
| `low_input` | INPUT_LOW warning, enrichment gaps (`data-enrichment-gaps`), degraded confidence visible; CTA is `next_action`, not prepare |
| `empty_shortlist` | No product name, no copy buttons, Shopify/Marketing disabled placeholders, no prepare CTA — nothing fake |

`learning_feedback` always renders as an explicit future placeholder
("FUTURO - DATOS EN VIVO NO CONECTADOS") with the observation schema slots.

## 5. Interactions (inline JS, local-only)

- Module rail + Marketing tabs: class toggling via event delegation.
- Copy buttons: `navigator.clipboard.writeText` with a textarea/execCommand
  fallback (works from file://). Copies the byte-exact payload text.
- Checkmarks (`data-local-check`): toggled visually and persisted only in
  `localStorage` under `r109b_checks_<fixture_id>`. Nothing is sent anywhere.
- No fetch-style calls, no XHR clients, no forms, no external script/link tags.

## 5b. System amplification layer (I1B-R2)

The recommended state renders the full commercial brain, all from existing
contract fields:

| Surface | Marker | Source fields |
|---|---|---|
| SYNAPSE Commercial Brief | `commercial_intelligence_brief` | decision, capability_surface_map, action_queue, shopify_pack.missing_inputs, claim_risk_by_copy |
| "Lo que SYNAPSE ya hizo" | `synapse_already_did` | economics, input_richness, shopify_pack, marketing_pack, claim_guard, candidate_pipeline, provenance, safety_boundary — items appear only when the field exists |
| Publish blockers | `publish_blockers` | shopify_pack.missing_inputs + medium claim_risk_by_copy + input_richness.missing_fields |
| Operator first move | `operator_first_move` | action_queue `is_primary` |
| Refusals | `synapse_refuses_to_do` | capability_surface_map.forbidden_to_claim + safety boundary |
| Anticipation Queue | `anticipation_queue` | action_queue enriched with target-module label/status/summary from module_status_summary (why / unlocks / risk prevented) |
| Capability Surface Strip | `capability_surface_strip` | capability_surface_map (4 tiers, compact chips) |
| Commercial Readiness Stack | `commercial_readiness_stack` | module_status_summary (7 steps: Product, Economics, Shopify, Marketing, Safety, Evidence, Learning) + per-module missing items from their contract sections |
| Shopify listing builder | `shopify_listing_builder`, `no_live_publish` | shopify_pack (identity / price / SEO / bullets / specs / FAQ / gaps / payloads) |
| Marketing war room | `marketing_war_room`, `rewrites_pending`, `testing_plan_with_thresholds`, `commercial_copy_support` | marketing_pack V2 fields; the technical `input_support_map` card renders only in the Evidence/Audit Drawer (R5) |
| Evidence black box | `evidence_black_box`, `provenance`, `safety_boundary` | provenance + safety_boundary + capability_surface_map |

The brief and snapshot are gated on `blocked_queue_summary.can_prepare`, so
they never render for blocked / low_input / empty_shortlist. The stack, strip,
and anticipation queue render for every state with that state's honest
statuses.

## 5c. Premium operator OS shell (I1B-R3)

R3 upgrades the visual layer to a premium operator OS: obsidian/graphite
surfaces, champagne-gold accents reserved for money and priority, steel blue
for audit/provenance, emerald only for safe/pass, red only for blocks, violet
only for future/learning. Same contract, same determinism.

| Surface | Markers | Notes |
|---|---|---|
| Operator session gate | `operator_session_gate`, `local_session_only`, `operator_alias_memory` | First-run overlay with a local operator alias and an explicit "No es autenticacion real; sesion local del navegador" disclaimer. Alias + dismissed state live only in `localStorage` (`r109b_operator_session`); a footer button resets the session. Never a security claim. |
| Top cockpit | `premium_top_cockpit`, `money_metrics_bar`, `safety_boundary_chip` | Product identity, commercial status, formatted money metrics (margin, breakeven CPA, price from `economics`), primary CTA, fixture/offline chip, boundary chip, alias chip (JS-filled). States without economics show an honest "sin metricas" note. |
| Executive operating brief | `executive_operating_brief`, `commercial_verdict_card`, `money_readiness_card`, `risk_control_card`, `trust_boundary_card` | The R2 brief restructured as verdict hero + money/readiness + risk-control cards, plus the existing already-did / blockers / first-move columns and the refusals as a trust boundary. Still gated on `can_prepare`. |
| Anticipation playbook | `anticipation_playbook`, `persisted_checklist`, `data-unlocks`, `data-prevents` | Each action shows priority chip, why it matters, what it unlocks, what risk it prevents, and its contract source; checks persist per-fixture in `localStorage`. |
| SYNAPSE brain map | `synapse_brain_map`, `system_capability_nodes` | Compact node map (Discovery, Financial evaluation, Product Lab, Shopify pack/publish, Marketing pack/Meta, Claim Guard, Evidence, Learning, Spend Guard, Fulfillment). Every node resolves its tier by membership in `capability_surface_map` (`real_now` / `fixture_only` / `future_or_not_connected` / `forbidden_to_claim`) or the `safety_boundary` flags — never renderer-invented. Renders in all states. |
| Premium Shopify builder | `premium_shopify_builder`, `listing_preview`, `publish_readiness_checklist`, `payload_drawer`, `shopify_payload_copy`, `no_live_publish` | Listing preview card (real fields + honest "imagen pendiente" gap), payload drawer with copy buttons. In blocked state the preview and drawer are omitted and the payload section renders only the suppressed placeholder — `shopify_payload_copy` never appears. |
| Marketing war room | `premium_marketing_war_room`, `strategy_snapshot`, `angle_cards`, `hooks_bank`, `ad_copy_console`, `channel_script_pack`, `no_spend_boundary`, `marketing_payload_copy` | Tabbed war room with an always-visible "SIN GASTO - SIN PUBLICACION EN META" boundary banner. `marketing_payload_copy` is likewise suppressed (absent) in blocked state. |
| Evidence black box | `premium_evidence_black_box`, `evidence_chain`, `deterministic_renderer`, `no_runtime_network` | Adds a deterministic evidence chain (frozen fixture + base head -> ViewModel -> renderer version -> static HTML) over the existing provenance / boundary / capability map cards. |
| Browser-local memory | `browser_local_memory`, `local_only_persistence` | `localStorage` holds only: operator alias, checklist completion, last module/lab tab (restored only when the default module is `command_center`, so blocked-first never gets overridden). Labeled in the footer as browser-local; no backend, no account, no security claim. |

State honesty is unchanged: blocked stays red-dominant with no prepare CTA,
no listing preview, no payload drawers, and no copy-ready payload markers;
low_input leads with enrichment; empty_shortlist renders no fake product,
payloads, previews, or money metrics.

## 5d. Functional operator workspace (I1B-R4)

R4 turns the premium shell into a functional offline workspace. Every
candidate render is wrapped in a `data-candidate-root="<fixture_id>"`
container so all browser-local memory is scoped per candidate.

**Candidate selector / workspace mode.** Command Center is the hub
(`command_center_hub`) and opens with a candidate selector
(`product_selector`, `candidate_switcher`, `candidate_list`,
`candidate_comparison`): compact cards with state badge, status, margin,
next action or primary blocker, and brief richness — all from existing
ViewModel fields. Single renders embed one candidate; workspace mode embeds
several fixture states in one HTML (`data-mode="workspace_mode"`), preparable
candidates sorted first and selected by default (`selected_candidate_state`).
Switching is pure local JS show/hide per candidate root; the selection
persists in `localStorage` (`r109b_workspace_state`).

```
python -m synapse.ui.operator_workbench_visual --fixture-dir tests/fixtures/a8_r109a --output runs/<run>/workspace.html
```

Both existing CLI modes keep working (`--fixture` + `--output`;
`--fixture-dir` + `--output-dir`).

**Editable operator drafts.** Shopify Studio gains a listing editor
(`listing_editor`: title, subtitle, operator price note, bullets, short/long
description, SEO title/meta) and Marketing an edit console (hooks, headlines,
primary texts, short/long ads, captions) plus manual observation notes;
Command Center has operator notes. Fields are inputs/textareas seeded with
the system output (`defaultValue`); edits persist per candidate in
`localStorage` (`r109b_drafts_<fixture_id>`), show an EDITADO chip
(`draft_dirty_state`), and each section has a reset button
(`reset_to_system_output`). Drafts never mutate the fixture or ViewModel and
never claim engine recomputation; the microcopy says so.

**Copy / export.** "Selling Packet Local" (`selling_packet_export`) renders
deterministic packet texts built only from contract fields: full selling
packet (`copy_full_selling_packet`; copying appends the operator's local
drafts under an explicit "drafts locales" header), Shopify listing packet,
marketing packet, supplier stock/cost confirmation message
(`supplier_confirmation_message`, also in Shopify Studio), and a claim-safe
copy packet. No network, no upload, no submit.

**Functional Marketing Engine.** New first tab "Primer Test"
(`functional_marketing_engine`): risk-adjusted first angle picked by lowest
`claim_risk` in `angle_matrix` (`recommended_first_angle`), copy priority
order derived from `claim_risk_by_copy` (`copy_priority_order`), rewrite
queue + claim-safe versions, manual test plan from both testing plans
(`manual_test_plan`), expected/failure signals and minimum evidence from
`creative_hypotheses`, "do not conclude" warnings, and a
`no_fake_performance_claims` banner. No analytics, no efficacy claims.

**Local progress.** Command Center shows checklist and draft progress
(`local_progress_summary`, `checklist_progress`, `draft_progress`), computed
client-side from local checks/drafts only and labeled as browser-local.

**State protections (R4).**

| State | Behavior |
|---|---|
| blocked | No editors (`blocked_editing_disabled`), repair/reject only (`repair_or_reject_only`), no selling packet (`data-packet-unavailable`), no supplier message, operator notes remain the only editable surface |
| low_input | `enrichment_workspace` in Product Lab with local enrichment notes; "Necesita enriquecimiento antes del sell-prep"; no full selling packet; marketing packet text carries the INPUT_LOW warning |
| empty_shortlist | `empty_state_no_product`; no editors, no packets, no copy buttons, honest next safe action |

`localStorage` keys after R4: `r109b_operator_session` (alias),
`r109b_checks_<fid>`, `r109b_tabs_<fid>`, `r109b_drafts_<fid>`,
`r109b_workspace_state` (selected candidate). All browser-local; no backend,
no account, no real authentication.

## 5e. Evidence separation (I1B-R5)

The commercial main stage and the technical audit are strictly separated.
The Evidence/Audit Drawer is delimited in the HTML by the
`<!--EVIDENCE_DRAWER_START-->` / `<!--EVIDENCE_DRAWER_END-->` comment markers
(one drawer per candidate shell), and it is the only place where these
technical surfaces render:

- `data-contract-section="input_support_map"` ("Mapa de soporte de inputs",
  raw output keys + source paths + missing marketing inputs)
- `data-contract-section="provenance"` (incl. `base_head`)
- `data-audit="source_fields"` (source fields ledger)
- `data-contract-section="capability_surface_map"` (full tier card)
- `data-audit="score_explanation"`
- `data-audit="assumptions_ledger"`

The Marketing Engine main stage (`lab_strategy`) replaces the technical
support map with a non-technical commercial summary
(`commercial_copy_support`, "Soporte comercial del copy"): which facts back
the strategy, which copy surfaces are data-backed vs generic, and what inputs
are missing before trusting the copy — operator language only, no source
paths, no raw field names, no internal logs.

Marker alignment: `recommended_first_angle` is the official marker for the
risk-adjusted first recommended angle. The shorter `recommended_angle` name
is not part of the contract and is never emitted as a marker attribute.

## 6. Stable markers

Generated HTML exposes: `operator_workbench_visual` (body `data-renderer`),
`r109b_visual_flow` (body `data-flow`), `module_rail` (nav id), snake_case
module section ids (`command_center` ... `blocked_queue`), and
`data-contract-section` attributes for `candidate_pipeline`, `action_queue`,
`system_health_board`, `blocked_queue_summary`, `capability_surface_map`,
`claim_guard`.

## 7. Forbidden tokens

Rendered output and R109B source files must not contain network/client tokens
(fetch calls, XHR clients, external script/link tags, absolute web URLs,
externally-posting forms) nor Python live-write tokens. The renderer re-uses
the R109A output scan and fails the render if a token appears; tests scan the
source files with tokens assembled from halves.

### CLI

```
python -m synapse.ui.operator_workbench_visual --fixture tests/fixtures/a8_r109a/recommended.json --output runs/a8_r109b_i1b_visual_flow/recommended.html

python -m synapse.ui.operator_workbench_visual --fixture-dir tests/fixtures/a8_r109a --output-dir runs/a8_r109b_i1b_visual_flow
```

Writing the output HTML locally is the CLI's only side effect.
