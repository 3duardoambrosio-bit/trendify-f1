from __future__ import annotations

import copy
import hashlib
import html
import json
from pathlib import Path
from typing import Any

import pytest

from synapse.integration.local_catalog_to_methodology import (
    enrich_local_catalog_fixture_with_methodology,
)
from synapse.ui.local_catalog_workspace import parse_catalog_csv
from synapse.ui.operator_workbench_renderer import (
    render_workbench_html,
    scan_forbidden_tokens,
)
from synapse.ui.operator_workbench_view_model import (
    build_view_model,
    build_view_model_from_path,
)
from synapse.ui.operator_workbench_visual import (
    render_visual_html,
    render_workspace_html,
)


ROOT = Path(__file__).resolve().parents[2]

NOMINAL_CSV = (
    ROOT
    / "tests"
    / "fixtures"
    / "a8_r110_catalog"
    / "catalog_nominal.csv"
)

CONTEXT_PATH = (
    ROOT
    / "tests"
    / "fixtures"
    / "a8_r111_methodology_context"
    / "nominal_context.json"
)

LEGACY_FIXTURE_DIR = (
    ROOT
    / "tests"
    / "fixtures"
    / "a8_r109a"
)

LEGACY_NAMES = (
    "recommended",
    "blocked",
    "low_input",
    "empty_shortlist",
)

LEGACY_AUDIT_SHA256 = {
    "recommended":
        "DC2D2EA76F5278E9C72084070FB04F7AC38EB458D7D6B5D0A48887B62C82026B",
    "blocked":
        "DB186AA06A5660F3F4E7C147E2274A30AA7BFE735DDDAC0A04A2AB75AFDCEB49",
    "low_input":
        "CC4A0F9AAF9F49076C4BEB3F81C7A6C91FC44244921F6B058B3CBDDCE4912F85",
    "empty_shortlist":
        "47FCD632D171B3E85FC97D1583EBD52A5E663ED842F752C3F88D76727FC6E8FE",
}

LEGACY_VISUAL_SHA256 = {
    "recommended":
        "D8E570E12E4A529F74BB40DA71D1B2C25B0F917CB755C5B234BB97BA1C605DE4",
    "blocked":
        "E1C7EB09CB88E45867CF032B5023E0B062D740D4A5724B0975499AAE27BAE4A0",
    "low_input":
        "7CB449555E618136675002E36202F9F1D37AD522F4D04AF19FB3D77BBEAC9E0E",
    "empty_shortlist":
        "09ADB64A5409484610D1E66C98306516E28ED484834FDB57FD75F89EB87A618C",
}

LEGACY_WORKSPACE_SHA256 = (
    "D939F56497EB4C1C8173155256C38E5CC2E769313FDEAC48EEAFEDBF67FDFD75"
)

RULE_FIELDS = (
    "rule_id",
    "framework",
    "source_anchor",
    "priority",
    "predicate_matched",
    "semantic_matched",
    "missing_fields",
    "triggers",
    "decision_text",
)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest().upper()


def _context() -> dict[str, Any]:
    return json.loads(
        CONTEXT_PATH.read_text(encoding="utf-8")
    )


def _enriched_fixture() -> dict[str, Any]:
    context = _context()
    result = parse_catalog_csv(NOMINAL_CSV)

    fixture = next(
        copy.deepcopy(dict(candidate))
        for candidate in result.fixtures
        if (
            candidate.get("product") or {}
        ).get("category") == context["category"]
    )

    return enrich_local_catalog_fixture_with_methodology(
        fixture,
        context,
    )


def _view_model(
    fixture: dict[str, Any] | None = None,
):
    materialized = fixture or _enriched_fixture()

    return build_view_model(
        materialized,
        source_fixture=NOMINAL_CSV.as_posix(),
    )


def _audit_panel(document: str) -> str:
    marker = '<section id="methodology-decision"'
    start = document.index(marker)
    end = document.index("</section>", start)
    return document[start : end + len("</section>")]


def _visual_panel(document: str) -> str:
    marker = '<div class="card methodology-decision"'
    end_marker = "<!-- methodology-decision:end -->"
    start = document.index(marker)
    end = document.index(end_marker, start)
    return document[start : end + len(end_marker)]


def _assert_read_only_panel(
    panel: str,
    *,
    operator_review_required: bool,
) -> None:
    for forbidden in (
        "data-copy-button",
        "data-copy-target",
        "data-cta",
        "data-draft-field",
        "contenteditable",
        "<textarea",
        "<input",
    ):
        assert forbidden not in panel

    review_marker = str(
        operator_review_required
    ).lower()

    assert 'data-methodology-present="true"' in panel
    assert 'data-permission-gate="REVIEW"' in panel
    assert (
        f'data-operator-review-required="{review_marker}"'
        in panel
    )
    assert 'data-safe-output-review-required="true"' in panel
    assert 'data-methodology-safe-output="inert"' in panel

    assert (
        "Salida del motor sellado. Requiere revisión "
        "del operador."
    ) in panel

    assert (
        "no autoriza publicación, gasto ni escrituras "
        "en vivo"
    ) in panel

    assert (
        "Cuando su valor es false, no elimina "
        "permission_gate=REVIEW."
    ) in panel


def test_nominal_bridge_renders_methodology_read_only() -> None:
    fixture = _enriched_fixture()
    view_model = _view_model(fixture)
    data = view_model.to_dict()

    methodology = data["decision"]["methodology"]

    assert data["decision"]["permission_gate"] == "REVIEW"
    assert methodology["operator_review_required"] is False
    assert data["shopify_pack"]["enabled"] is False
    assert data["marketing_pack"]["enabled"] is False

    audit = render_workbench_html(view_model)
    visual = render_visual_html(view_model)

    second_fixture = copy.deepcopy(fixture)
    second_fixture["fixture_id"] += "_workspace_copy"
    second_view_model = _view_model(second_fixture)

    workspace = render_workspace_html(
        [view_model, second_view_model]
    )

    audit_panel = _audit_panel(audit)
    visual_panel = _visual_panel(visual)

    _assert_read_only_panel(
        audit_panel,
        operator_review_required=False,
    )
    _assert_read_only_panel(
        visual_panel,
        operator_review_required=False,
    )

    assert workspace.count(
        'data-contract-section="methodology_decision"'
    ) == 2

    for field in (
        "permission_gate",
        "schema_version",
        "status",
        "selected_rule_id",
        "selected_framework",
        "operator_review_required",
        "triggers",
        "rule_decisions",
        "safe_output",
    ):
        assert field in audit_panel
        assert field in visual_panel

    tabular_rule_fields = (
        "rule_id",
        "framework",
        "source_anchor",
        "priority",
        "predicate_matched",
        "semantic_matched",
        "decision_text",
    )

    listed_rule_fields = (
        "missing_fields",
        "triggers",
    )

    for field in tabular_rule_fields:
        assert f"<th>{field}</th>" in audit_panel
        assert f"<th>{field}</th>" in visual_panel

    for field in listed_rule_fields:
        assert f"<h4>{field}</h4>" in audit_panel
        assert f"<h4>{field}</h4>" in visual_panel

    escaped_output = html.escape(
        methodology["safe_output"],
        quote=True,
    )

    assert escaped_output in audit_panel
    assert escaped_output in visual_panel

    assert scan_forbidden_tokens(audit) == []
    assert scan_forbidden_tokens(visual) == []
    assert scan_forbidden_tokens(workspace) == []


def test_safe_output_is_escaped_and_inert() -> None:
    fixture = _enriched_fixture()

    fixture["decision"]["methodology"]["safe_output"] = (
        "<em>unsafe & inert</em>"
    )

    view_model = _view_model(fixture)

    audit_panel = _audit_panel(
        render_workbench_html(view_model)
    )

    visual_panel = _visual_panel(
        render_visual_html(view_model)
    )

    escaped = "&lt;em&gt;unsafe &amp; inert&lt;/em&gt;"

    assert escaped in audit_panel
    assert escaped in visual_panel
    assert "<em>unsafe & inert</em>" not in audit_panel
    assert "<em>unsafe & inert</em>" not in visual_panel

    _assert_read_only_panel(
        audit_panel,
        operator_review_required=False,
    )
    _assert_read_only_panel(
        visual_panel,
        operator_review_required=False,
    )


def test_methodology_rendering_is_deterministic() -> None:
    first = _view_model()
    second_fixture = _enriched_fixture()
    second_fixture["fixture_id"] += "_second"
    second = _view_model(second_fixture)

    assert (
        render_workbench_html(first)
        == render_workbench_html(first)
    )

    assert (
        render_visual_html(first)
        == render_visual_html(first)
    )

    assert (
        render_workspace_html([first, second])
        == render_workspace_html([first, second])
    )



def test_true_operator_review_flag_is_preserved() -> None:
    fixture = _enriched_fixture()

    fixture["decision"]["methodology"][
        "operator_review_required"
    ] = True

    view_model = _view_model(fixture)
    data = view_model.to_dict()

    assert (
        data["decision"]["methodology"][
            "operator_review_required"
        ]
        is True
    )

    audit = render_workbench_html(view_model)
    visual = render_visual_html(view_model)
    workspace = render_workspace_html([view_model])

    audit_panel = _audit_panel(audit)
    visual_panel = _visual_panel(visual)

    _assert_read_only_panel(
        audit_panel,
        operator_review_required=True,
    )
    _assert_read_only_panel(
        visual_panel,
        operator_review_required=True,
    )

    assert (
        workspace.count(
            'data-operator-review-required="true"'
        )
        == 1
    )

    assert (
        workspace.count(
            'data-safe-output-review-required="true"'
        )
        == 1
    )


@pytest.mark.parametrize(
    "case",
    (
        "empty_mapping",
        "missing_field",
        "wrong_gate",
        "review_not_bool",
        "triggers_string",
        "rules_string",
        "rule_not_mapping",
        "rule_missing_field",
        "safe_output_not_text",
    ),
)
def test_malformed_present_methodology_fails_closed(
    case: str,
) -> None:
    fixture = _enriched_fixture()
    methodology = fixture["decision"]["methodology"]

    if case == "empty_mapping":
        fixture["decision"]["methodology"] = {}
    elif case == "missing_field":
        methodology.pop("schema_version")
    elif case == "wrong_gate":
        fixture["decision"]["permission_gate"] = "PASS"
    elif case == "review_not_bool":
        methodology["operator_review_required"] = "not-bool"
    elif case == "triggers_string":
        methodology["triggers"] = "not-a-sequence"
    elif case == "rules_string":
        methodology["rule_decisions"] = "not-a-sequence"
    elif case == "rule_not_mapping":
        methodology["rule_decisions"][0] = "not-a-mapping"
    elif case == "rule_missing_field":
        methodology["rule_decisions"][0].pop("framework")
    elif case == "safe_output_not_text":
        methodology["safe_output"] = ["not", "text"]
    else:
        raise AssertionError(case)

    view_model = _view_model(fixture)

    for renderer in (
        render_workbench_html,
        render_visual_html,
    ):
        with pytest.raises(ValueError, match="methodology"):
            renderer(view_model)

    with pytest.raises(ValueError, match="methodology"):
        render_workspace_html([view_model])


@pytest.mark.parametrize("name", LEGACY_NAMES)
def test_legacy_single_render_hashes_remain_exact(
    name: str,
) -> None:
    view_model = build_view_model_from_path(
        LEGACY_FIXTURE_DIR / f"{name}.json"
    )

    data = view_model.to_dict()

    assert "methodology" not in data["decision"]

    audit = render_workbench_html(view_model)
    visual = render_visual_html(view_model)

    assert (
        _sha256_text(audit)
        == LEGACY_AUDIT_SHA256[name]
    )

    assert (
        _sha256_text(visual)
        == LEGACY_VISUAL_SHA256[name]
    )

    assert "methodology-decision" not in audit

    assert (
        'data-contract-section="methodology_decision"'
        not in visual
    )


def test_legacy_workspace_hash_remains_exact() -> None:
    view_models = [
        build_view_model_from_path(
            LEGACY_FIXTURE_DIR / f"{name}.json"
        )
        for name in LEGACY_NAMES
    ]

    workspace = render_workspace_html(view_models)

    assert (
        _sha256_text(workspace)
        == LEGACY_WORKSPACE_SHA256
    )

    assert (
        'data-contract-section="methodology_decision"'
        not in workspace
    )


def test_renderers_do_not_call_methodology_producers() -> None:
    runtime_paths = (
        ROOT
        / "synapse"
        / "ui"
        / "operator_workbench_renderer.py",
        ROOT
        / "synapse"
        / "ui"
        / "operator_workbench_visual.py",
    )

    for path in runtime_paths:
        source = path.read_text(encoding="utf-8")

        for forbidden_dependency in (
            "local_catalog_to_methodology",
            "methodology_decision_engine",
            "load_methodology_contract",
            "decide_marketing_methodology",
            "expert_foundation",
            "brief_builder",
        ):
            assert forbidden_dependency not in source
