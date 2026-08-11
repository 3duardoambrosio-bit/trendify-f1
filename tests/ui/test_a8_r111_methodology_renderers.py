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
    load_fixture,
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

LEGACY_SOURCE_DIR = (
    Path("tests")
    / "fixtures"
    / "a8_r109a"
)

LEGACY_FIXTURE_DIR = (
    ROOT
    / LEGACY_SOURCE_DIR
)

LEGACY_NAMES = (
    "recommended",
    "blocked",
    "low_input",
    "empty_shortlist",
)

LEGACY_AUDIT_SHA256 = {
    "recommended":
        "0230B9EFBCD84913741777C69B2399C4E2E001A9A9BC47044F009F5EB5696211",
    "blocked":
        "2FDADE30040F3F8025CFB56CE4A2C690B1A8EE71A40760B6C6E098BB071836D8",
    "low_input":
        "0EB041D3813483B46AB3B7473E4F67C36079DEF8EE1F29D789E635157D018CAC",
    "empty_shortlist":
        "D017C5DC5FDF39D87BE93C6F9E8EA933FF62037BACE7EED783B45273D3ABA47B",
}

LEGACY_VISUAL_SHA256 = {
    "recommended":
        "BACFF1C0AE5CDAFC9B79026EC5E9139D116EDD9A865782ED31C2C3F99DA8FA51",
    "blocked":
        "67BBBC5D202D2551E358D81BB36F81A182D9C0A9944B73B8D24DA5A95E10AFB4",
    "low_input":
        "1788B0FBE48760672996793B958ED79094F9B013A2777A746E20CFD13280293C",
    "empty_shortlist":
        "22B89B14C9700DB20D2073A0219C6645A7DCC06318491BD33488F8AA286C71F5",
}

LEGACY_WORKSPACE_SHA256 = (
    "0C477D2FF655D4A7481D424FFD93B7FC45E01DF803DECDC47405E342A56D6386"
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


def _legacy_view_model(
    name: str,
    *,
    fixture_dir: Path = LEGACY_FIXTURE_DIR,
):
    fixture_path = fixture_dir / f"{name}.json"

    return build_view_model(
        load_fixture(fixture_path),
        source_fixture=(
            LEGACY_SOURCE_DIR / f"{name}.json"
        ).as_posix(),
    )


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
    raw_methodology: bool = True,
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
    if raw_methodology:
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
    else:
        assert 'data-methodology-safe-output="inert"' not in panel
        assert "Resumen metodológico para el operador" in panel
        assert "nunca autoriza publicación, gasto ni escrituras en vivo" in panel
        assert "safe_output" not in panel


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
        raw_methodology=False,
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

    assert "Resumen metodológico para el operador" in visual_panel
    assert "ACEPTADO PARA PREPARACIÓN LOCAL" in visual_panel

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
        assert f"<th>{field}</th>" not in visual_panel

    for field in listed_rule_fields:
        assert f"<h4>{field}</h4>" in audit_panel
        assert f"<h4>{field}</h4>" not in visual_panel

    escaped_output = html.escape(
        methodology["safe_output"],
        quote=True,
    )

    assert escaped_output in audit_panel
    assert escaped_output not in visual_panel

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
    assert escaped not in visual_panel
    assert "<em>unsafe & inert</em>" not in audit_panel
    assert "<em>unsafe & inert</em>" not in visual_panel

    _assert_read_only_panel(
        audit_panel,
        operator_review_required=False,
    )
    _assert_read_only_panel(
        visual_panel,
        operator_review_required=False,
        raw_methodology=False,
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
        raw_methodology=False,
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
    view_model = _legacy_view_model(name)

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
        _legacy_view_model(name)
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


def test_legacy_hashes_ignore_absolute_fixture_root(
    tmp_path: Path,
) -> None:
    relocated_dir = tmp_path / "relocated" / "a8_r109a"
    relocated_dir.mkdir(parents=True)

    source_path = LEGACY_FIXTURE_DIR / "recommended.json"
    relocated_path = relocated_dir / source_path.name
    relocated_path.write_bytes(source_path.read_bytes())

    canonical = _legacy_view_model("recommended")
    relocated = _legacy_view_model(
        "recommended",
        fixture_dir=relocated_dir,
    )

    assert canonical.to_json() == relocated.to_json()

    assert (
        render_workbench_html(canonical)
        == render_workbench_html(relocated)
    )

    assert (
        render_visual_html(canonical)
        == render_visual_html(relocated)
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
