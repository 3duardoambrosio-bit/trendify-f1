"""A8-R113.2 — functional-truth gate for the local Operator Workbench.

No browser/network/live connector is required. These tests verify deterministic
markup contracts and the interaction kernel embedded in the generated HTML.
"""

from __future__ import annotations

import json
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from synapse.ui import operator_workbench_view_model as wb_vm
from synapse.ui import operator_workbench_visual as wb_visual

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "a8_r109a"


class _MarkupInventory(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.controls: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: value or "" for name, value in attrs}
        identifier = attributes.get("id")
        if identifier:
            self.ids.append(identifier)
        if tag in {"button", "input", "select", "textarea"}:
            self.controls.append((tag, attributes))


def _build(name: str) -> wb_vm.WorkbenchViewModel:
    return wb_vm.build_view_model_from_path(FIXTURE_DIR / f"{name}.json")


def _inventory(document: str) -> _MarkupInventory:
    parser = _MarkupInventory()
    parser.feed(document)
    return parser


def _has_interaction_contract(tag: str, attributes: dict[str, str]) -> bool:
    contract_attributes = {
        "data-gate-enter",
        "data-session-reset",
        "data-drawer-open",
        "data-drawer-close",
        "data-filter",
        "data-sort",
        "data-draft-reset",
        "data-copy-button",
        "data-candidate-select",
        "data-local-check",
        "data-lab-tab",
        "data-nav-module",
        "data-select-angle",
        "data-draft-field",
    }
    if any(name in attributes for name in contract_attributes):
        return True
    return tag == "input" and attributes.get("id") == "operator_alias_input"


def test_interaction_kernel_defines_every_required_behavior() -> None:
    source = Path(wb_visual.__file__).read_text(encoding="utf-8")
    for function_name in (
        "applyCandidateFilter",
        "applyCandidateSort",
        "updateEffectiveField",
        "resetDraftSection",
        "enterWorkbench",
        "openDrawer",
        "closeDrawer",
        "toggleCheck",
        "activateLabPanel",
    ):
        assert f"function {function_name}" in source

    for selector in (
        '[data-filter]',
        '[data-sort]',
        '[data-draft-field]',
        '[data-drawer-open]',
        '[data-drawer-close]',
        '[data-local-check]',
        '[data-lab-tab]',
        '[data-nav-module]',
    ):
        assert selector in source


def test_single_candidate_does_not_render_dead_filter_or_sort_controls() -> None:
    document = wb_visual.render_visual_html(_build("low_input"))
    inventory = _inventory(document)
    assert not any("data-filter" in attributes for _, attributes in inventory.controls)
    assert not any("data-sort" in attributes for _, attributes in inventory.controls)
    assert 'data-selector-single="true"' in document


def test_workspace_renders_real_filter_and_sort_controls() -> None:
    document = wb_visual.render_workspace_html([_build("recommended"), _build("low_input")])
    inventory = _inventory(document)
    filter_controls = [attrs for _, attrs in inventory.controls if "data-filter" in attrs]
    sort_controls = [attrs for _, attrs in inventory.controls if "data-sort" in attrs]
    assert {attrs["data-filter"] for attrs in filter_controls} == {
        "all", "recommended", "blocked", "low_input", "empty"
    }
    assert {attrs["data-sort"] for attrs in sort_controls} == {
        "score", "margin", "risk", "state"
    }
    assert "applyCandidateFilter" in document
    assert "applyCandidateSort" in document


def test_every_formal_control_has_an_interaction_contract() -> None:
    document = wb_visual.render_workspace_html([_build("recommended"), _build("low_input")])
    inventory = _inventory(document)
    missing = [
        (tag, attributes)
        for tag, attributes in inventory.controls
        if not _has_interaction_contract(tag, attributes)
    ]
    assert missing == []


def test_workspace_has_no_duplicate_dom_ids() -> None:
    document = wb_visual.render_workspace_html([_build("recommended"), _build("low_input")])
    ids = _inventory(document).ids
    duplicates = sorted(identifier for identifier, count in Counter(ids).items() if count > 1)
    assert duplicates == []


def test_draft_fields_are_labelled_and_have_effective_targets() -> None:
    document = wb_visual.render_visual_html(_build("recommended"))
    inventory = _inventory(document)
    draft_controls = [attrs for _, attrs in inventory.controls if "data-draft-field" in attrs]
    assert draft_controls
    for attributes in draft_controls:
        assert attributes.get("id")
        assert f'for="{attributes["id"]}"' in document

    for field_name in (
        "shopify_title",
        "shopify_subtitle",
        "shopify_bullets",
        "shopify_short_description",
        "shopify_long_description",
        "shopify_seo_title",
        "shopify_seo_meta_description",
        "marketing_hooks",
        "marketing_short_ads",
        "marketing_long_ads",
    ):
        assert f'data-effective-field="{field_name}"' in document


def test_full_pack_copy_declares_operator_override_appendix() -> None:
    document = wb_visual.render_visual_html(_build("recommended"))
    assert 'data-payload-key="shopify_full_pack"' in document
    assert 'data-payload-key="marketing_full_pack"' in document
    assert document.count("data-append-drafts") >= 2
    assert "OVERRIDES EFECTIVOS DEL OPERADOR" in document


def test_context_gate_is_not_presented_as_authentication() -> None:
    document = wb_visual.render_visual_html(_build("recommended"))
    assert "Contexto local del operador" in document
    assert "Abrir Workbench" in document
    assert "No es un inicio de sesion ni autenticacion" in document
    assert "Entrar al Workbench" not in document


def test_tabs_and_drawer_expose_keyboard_and_dialog_semantics() -> None:
    document = wb_visual.render_visual_html(_build("recommended"))
    assert 'role="tab"' in document
    assert 'aria-selected="true"' in document
    assert 'role="tabpanel"' in document or "setAttribute(\"role\", \"tabpanel\")" in document
    assert 'role="dialog"' in document
    assert 'aria-modal="true"' in document
    assert 'event.key === "Escape"' in document
    keyboard_gate = (
        '["ArrowLeft", "ArrowRight", "Home", "End"]'
        ".indexOf(event.key) !== -1"
    )
    assert keyboard_gate in document
    assert 'event.key === "Home"' in document
    assert 'event.key === "End"' in document
    assert 'else { index = (index + 1) % tabs.length; }' in document


def test_publication_boundary_is_not_counted_as_preparation_gap() -> None:
    shopify_pack = {
        "enabled": True,
        "missing_inputs": ["variants_not_modeled", "publication_not_authorized"],
        "publish_checklist": ["Review local draft."],
    }
    preparation, boundaries = wb_visual._shopify_gap_split(shopify_pack)
    assert preparation == ["variants_not_modeled"]
    assert boundaries == ["publication_not_authorized"]

    summary = wb_vm.build_module_status_summary(
        fixture={
            "decision": {
                "outcome": "REVIEW_REQUIRED",
                "reason": "operator review",
                "reason_codes": ["PASS_HEALTHY_UNIT_ECONOMICS"],
            },
            "economics": {},
        },
        claim_guard={
            "allowed_claims": [],
            "risky_claims": [],
            "prohibited_claims": [],
            "safe_wording": [],
        },
        input_richness={
            "classification": "INPUT_LOW",
            "filled_count": 2,
            "total_fields": 10,
            "missing_fields": ["target_audience"],
        },
        shopify_pack=shopify_pack,
        marketing_pack={"enabled": False},
        blocked_queue=[],
        operator_actions=[],
        has_product=True,
    )
    module = next(item for item in summary if item["module_id"] == "shopify_studio")
    assert module["badge_text"] == "1 GAP / SIN PUBLICAR"


def test_pass_reason_codes_are_never_rendered_as_blockers() -> None:
    fixture_path = FIXTURE_DIR / "low_input.json"
    fixture: dict[str, Any] = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture["decision"]["reason_codes"].append("PASS_HEALTHY_UNIT_ECONOMICS")
    view_model = wb_vm.build_view_model(fixture, source_fixture=fixture_path.name)
    document = wb_visual.render_visual_html(view_model)
    drivers_start = document.index('data-drivers="top_drivers"')
    blockers_start = document.index('data-blockers="top_blockers"', drivers_start)
    next_card_boundary = document.index('class="sc-next"', blockers_start)
    drivers_html = document[drivers_start:blockers_start]
    blockers_html = document[blockers_start:next_card_boundary]
    assert "PASS_HEALTHY_UNIT_ECONOMICS" in drivers_html
    assert "PASS_HEALTHY_UNIT_ECONOMICS" not in blockers_html


def test_economics_verdict_is_separate_from_input_richness() -> None:
    data = _build("low_input").to_dict()
    verdict, _tone, _reason = wb_visual._economics_verdict(data)
    assert verdict in {"PASS", "FAIL", "KILL", "SIN DATOS"}
    assert not (verdict == "WATCH" and data["input_richness"]["classification"] == "INPUT_LOW")


def test_current_adapter_can_override_historical_provenance_without_breaking_legacy() -> None:
    fixture_path = FIXTURE_DIR / "low_input.json"
    fixture: dict[str, Any] = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture["provenance"] = {
        "adapter_status": "system_checkpoint_projection_adapter",
        "base_head": "f" * 40,
        "fase_1_status": "checkpoint_local_pending_external_audit",
        "island": "A8-R113.2",
        "worktree_state": "dirty_source_hashes_required",
    }
    current = wb_vm.build_view_model(fixture, source_fixture="synthetic-current.json").to_dict()
    assert current["provenance"]["adapter_status"] == "system_checkpoint_projection_adapter"
    assert current["provenance"]["base_head"] == "f" * 40
    assert current["provenance"]["island"] == "A8-R113.2"

    legacy = _build("low_input").to_dict()
    assert legacy["provenance"]["adapter_status"] == "frozen_fixture_adapter"
    assert legacy["provenance"]["island"] == "A8-R109A"


def test_primary_checkpoint_action_maps_to_evidence() -> None:
    assert wb_vm.ACTION_KIND_TO_MODULE["review_checkpoint"] == "evidence"
    assert wb_vm.ACTION_KIND_TO_MODULE["review_shopify_draft"] == "shopify_studio"
