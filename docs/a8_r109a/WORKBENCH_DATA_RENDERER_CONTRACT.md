# A8-R109A — Workbench Data Contract + Deterministic Offline Renderer

## 1. Scope

A8-R109A builds the auditable mechanical foundation for the future SYNAPSE
Operator Workbench:

```
frozen fixtures (tests/fixtures/a8_r109a/)
  -> deterministic ViewModel (synapse/ui/operator_workbench_view_model.py)
  -> self-contained offline HTML renderer (synapse/ui/operator_workbench_renderer.py)
  -> exact copy payloads
  -> provenance/safety scans
  -> tests (tests/ui/test_a8_r109a_workbench_data_renderer.py)
```

This is NOT the final professional UI. It is the trustworthy data/rendering
contract that R109B will style later. There is no server, no Streamlit, no
live backend, no network, no credentials, and no runtime clock.

## 2. ViewModel contract

`build_view_model_from_path(fixture_path)` returns a frozen dataclass
`WorkbenchViewModel` with exactly these top-level fields:

| Field | Content |
|---|---|
| `schema_version` | `a8-r109a.workbench_view_model.v1` |
| `fixture_id` | Fixture identity (`a8_r109a_<scenario>`) |
| `render_mode` | `offline_static_html` |
| `source_kind` | `frozen_local_fixture` |
| `generated_at_policy` | `deterministic_no_runtime_clock` (no wall-clock anywhere) |
| `product` | Product identity or `{}` when the shortlist is empty |
| `decision` | Outcome, permission gate, reason, reason codes, caveats |
| `economics` | Local fixture economics (Decimal-free display copy, MXN) |
| `scores` | Local evaluation scores |
| `input_richness` | R105.3 classification (see below) |
| `claim_guard` | `allowed_claims`, `risky_claims`, `prohibited_claims`, `safe_wording`, `claim_guard_summary` |
| `shopify_pack` | Full store-preparation pack + `claim_guard_notes` (adjacency) |
| `marketing_pack` | Full marketing pack + `claim_guard` notes + `confidence` + `input_richness_warning` |
| `learning_plan` | Hypotheses/evidence/kill-continue criteria + `no_pmf_claim`, `no_analytics_fetch`, `operator_in_control` |
| `blocked_queue` | Blocked items with reasons, severity, operator actions, recoverability |
| `operator_actions` | Normalized operator actions (including auto-generated enrichment actions) |
| `provenance` | Seal: source fixture, adapter status, base head, island, determinism flags |
| `safety_boundary` | Twelve Fase 1 booleans, all `True` (read-only / dry-run / no live / no spend) |
| `evidence` | Evidence notes and artifact pointers |
| `copy_payloads` | Canonical copy registry (see below) |

Determinism: repeated builds of the same fixture produce equal dataclasses and
byte-identical `to_json()` output. There is no timestamp, no randomness, and
no environment-dependent value in the ViewModel.

## 3. Fixtures (frozen acceptance states)

| Fixture | State it freezes |
|---|---|
| `recommended.json` | Product that can proceed to prepare; rich brief; one risky claim; caveats; missing inputs (not overly perfect) |
| `blocked.json` | Product blocked by prohibited health claims + margin below floor; repair/reject operator actions; appears in `blocked_queue` |
| `low_input.json` | Poor operator brief; classified `INPUT_LOW`; generic low-confidence copy; enrichment actions (R105.3 operationalized) |
| `empty_shortlist.json` | No product; explains next action; copy payloads disabled with reason; safety/provenance/evidence shell intact |

## 4. Input richness (R105.3 operationalized)

Ten brief fields are scored (`target_audience`, `pain_points`, `desires`,
`objections`, `differentiators`, `tone_of_voice`, `market_context`,
`customer_language`, `proof_elements`, `competitor_notes`):

- 8-10 filled -> `INPUT_RICH`
- 4-7 filled -> `INPUT_PARTIAL`
- 0-3 filled -> `INPUT_LOW`

For `INPUT_LOW`:

- `marketing_pack.confidence` is `low` / `generic_low_confidence` with
  `expert_method_applied: false` (never claims expert quality),
- the ViewModel and the rendered HTML carry the warning
  "Input richness is low; enrich operator input before trusting marketing copy.",
- `operator_actions` gains `enrich_input` actions for the missing brief fields.

Rich brief -> stronger expert output. Poor brief -> generic/low-confidence output.

## 4b. Marketing Pack V2 depth (A8-R109A-I2)

Schema version is now `a8-r109a.workbench_view_model.v2`. Beyond the V1
fields, `marketing_pack` carries structural depth for the future R109B
Marketing Command Lab:

| Field | Content |
|---|---|
| `angle_matrix` | Angles with `angle_id`, `angle_name`, `promise_type`, `target_segment`, pain/desire/objection addressed, `proof_needed`, `claim_risk`, `safe_wording`, and the mandatory honesty pair `why_it_might_work` / `why_it_might_fail` |
| `creative_hypotheses` | Testable hypotheses with `hypothesis_id`, `variable_tested`, `expected_signal`, `failure_signal`, `minimum_evidence_needed`, `channel`, `linked_angle_id` (must link a real angle) |
| `claim_risk_by_copy` | One entry per major copy surface (`hooks`, `headlines`, `primary_texts`, `short_ads`, `long_ads`): `risk_level`, `risky_terms`, `prohibited_terms`, `safe_rewrite`, `reason`. Missing surfaces get a conservative `review` default derived from the claim guard |
| `input_support_map` | Maps every marketing output back to the fixture/operator-input fields that actually support it; unsupported outputs are flagged `NO SOPORTADO: fallback generico` and must never be read as claims |
| `missing_marketing_inputs` | Explicit list of empty brief fields and marketing seeds (`operator_input.*`, `marketing.*`) |
| `confidence_by_section` | Six graded scores (`strategy`, `hook`, `ad_copy`, `channel_pack`, `claim_safety`, `testing_plan`), derived from input richness, seed depth, and claim risk — never one global value. Blocked products force `claim_safety_confidence = blocked` |
| `testing_plan_with_thresholds` | `first_test_budget_boundary_dry_run_only` (theoretical boundary; Fase 1 is dry-run, no real spend), success/warning/stop signals, continue/review/kill criteria, `what_not_to_conclude`, `no_pmf_claim: true`, `no_analytics_fetch: true` |

A new canonical copy payload `marketing_full_pack_v2` serializes all of the
above deterministically; the recommended fixture's payload is asserted
byte-for-byte. Fixture behavior: recommended carries 3 angles, 3 hypotheses,
5 hooks; blocked constrains marketing with all-prohibited copy risk; low_input
degrades every section confidence to `low` and lists missing marketing inputs;
empty_shortlist renders none of it.

## 4c. System surface extension (A8-R109A.1)

Schema version is now `a8-r109a.workbench_view_model.v3`. Six new top-level
surfaces let R109B render real system density without inferring or faking it:

| Field | Content |
|---|---|
| `module_status_summary` | Ten modules in fixed order (`command_center`, `decision_center`, `product_lab`, `economics`, `shopify_studio`, `marketing_engine`, `safety_claim_guard`, `evidence`, `learning_feedback`, `blocked_queue`), each with `module_id`, `label`, `status` (`pass` / `warning` / `blocked` / `empty` / `future` / `audit`), `badge_text`, `summary`, `operator_action`, `source_fields`, `is_real_now`, `is_future_placeholder`. `learning_feedback` is always `future` (`is_real_now: false`); `evidence` is always `audit` |
| `candidate_pipeline` | Fixture-honest pipeline summary: scenario-derived counts (`total_candidates`, `recommended_count`, `blocked_count`, `low_input_count`, `empty_count`), `current_candidate_id`/`rank`, `pipeline_stage` (`prepare_for_sale` / `blocked_review` / `enrich_brief` / `await_shortlist`), `source: fixture_scenario`, `confidence: limited_fixture_only`, `live_discovery_connected: false`. It never claims live discovery |
| `blocked_queue_summary` | `blocked_count`, compact `blocked_items`, deduplicated `reason_codes`, `required_operator_actions`, `can_prepare` (true only for `RECOMMENDED_FOR_PREPARE`). Exposed on every fixture, including zero-item states |
| `action_queue` | Ordered actions with `action_id`, `label`, `reason`, `target_module` (mapped from action kind), `priority`, `source_fields`, and exactly one `is_primary: true` — the UI must not infer the next action |
| `system_health_board` | Fase 1 booleans (`offline_mode`, `no_live_writes`, `no_spend`, `no_fulfillment`, `no_credentials`) plus derived statuses for claim guard, input richness, Shopify pack, marketing pack, and evidence |
| `capability_surface_map` | Static honesty tiers: `real_now`, `fixture_only`, `future_or_not_connected`, `forbidden_to_claim` (includes `product_market_fit`, `live_analytics_connected`, `autonomous_spend`). Identical for all fixtures so the UI cannot overpromise |

All six surfaces derive deterministically from existing fixture content — no
fixture changes were needed, no live data is read, and every derived summary
cites its `source_fields`. The audit renderer gained matching sections
(`module-status-summary`, `candidate-pipeline`, `action-queue`,
`blocked-queue-summary`, `system-health-board`, `capability-surface-map`).

## 5. Blocked queue

Every ViewModel has a `blocked_queue` (possibly empty). Each item carries
`product_name`, `reason`, `reason_codes`, `severity`, `operator_actions`
(repair and reject paths), `can_recover`, and a per-item `safety_boundary`
(no live writes, no spend, operator decision required).

## 6. Claim guard adjacency

Claim guard data is not only global: `shopify_pack.claim_guard_notes` and
`marketing_pack.claim_guard` embed the relevant notes with an `adjacent_to`
marker, and the renderer places a `claim-guard-adjacent` block inside the
Shopify section and inside the Marketing section, next to the copy surfaces
R109B will style. Tests assert this adjacency in the rendered HTML.

## 7. Copy payloads

`copy_payloads` is a registry: `{enabled, disabled_reason, count, items}`.
Each item is `{key, label, section, text, claim_guard_ref, source_fields}`.

Canonical keys: `shopify_title`, `shopify_price`, `shopify_short_description`,
`shopify_long_description`, `shopify_bullets`, `shopify_full_pack`,
`marketing_hooks`, `marketing_short_ads`, `marketing_long_ads`,
`marketing_full_pack`, `learning_snapshot`, `safety_summary`.

For `empty_shortlist` the registry is explicitly disabled with
`disabled_reason = no_recommended_product_in_shortlist` and zero items; no
fake product copy is ever generated. Tests assert byte-for-byte payload text
for the recommended fixture (`shopify_title`, `shopify_full_pack`,
`marketing_full_pack`).

## 8. Renderer

`render_workbench_html(view_model)` produces one self-contained HTML string,
openable directly from disk (file protocol). Constraints enforced by a
built-in output scan (render fails if violated) and by tests:

- no script tags, no external stylesheets, fonts, or assets,
- no network client calls and no absolute web URLs of any kind,
- no forms posting anywhere,
- minimal inline CSS for readability only (visual polish belongs to R109B).

Rendered sections, in order: Provenance Seal, Product/Decision, Input
Richness, Economics/Scores, Shopify Pack (+ adjacent Claim Guard), Marketing
Pack (+ adjacent Claim Guard), Learning Plan, Blocked Queue, Operator
Actions, Safety Boundary, Evidence Notes, Copy Payload Registry.

### CLI

```
python -m synapse.ui.operator_workbench_renderer --fixture tests/fixtures/a8_r109a/recommended.json --output runs/a8_r109a_i1_renderer/recommended.html

python -m synapse.ui.operator_workbench_renderer --fixture-dir tests/fixtures/a8_r109a --output-dir runs/a8_r109a_i1_renderer
```

Writing the output HTML locally is the CLI's only side effect.

## 9. Forbidden tokens

New R109A files and rendered HTML must not contain network/client tokens
(fetch calls, XHR clients, external script/link tags, absolute web URLs,
externally-posting forms) nor Python live-write tokens (HTTP post helpers,
Shopify order forwarding, product creation, campaign publishing). The tests
scan both the R109A source files and the rendered output; scan tokens are
assembled from halves so the scanners never contain the literals themselves.

## 10. Safety boundary

Fase 1 boundary holds everywhere: read-only, dry-run, no live writes, no
spend, no fulfillment, no Shopify/Dropi/Meta live, no credentials, no
external network, operator in control, and an explicit future gate required
for anything live. The rendered HTML carries a visible provenance seal with
`base_head c189cb09f963417596f2b6a02bfbd9e9ae2459a2`, island `A8-R109A`, and
the determinism flags.
