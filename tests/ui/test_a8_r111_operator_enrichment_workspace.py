from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path

from synapse.ui.operator_enrichment_cli import (
    create_template,
    rebuild_workspace,
)
from synapse.ui.operator_workbench_view_model import build_view_model


def _write_csv(path: Path, *, category: str = "hogar_y_oficina") -> Path:
    path.write_text(
        "\n".join(
            (
                "product_id,title,supplier,category,supplier_price_mxn,"
                "shipping_cost_mxn,sale_price_mxn,payment_fee_mxn,source_url,notes",
                f"cat-001,Organizador de Cables Compacto,Proveedor MX Alfa,{category},"
                "120,40,399,15,,catalogo local",
            )
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _fill_template(path: Path, *, claim_risk: str = "low") -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(
        {
            "buyer_pain": "Cables sueltos ocupan espacio y dificultan ordenar el escritorio.",
            "buyer_state": "problem-aware",
            "target_audience": "Personas con escritorio de trabajo en casa.",
            "objections": ["Duda sobre el tamaÃ±o real del organizador."],
            "proof_available": [
                "Registro CSV local del operador con identidad y costos completos"
            ],
            "product_facts": [
                "Identidad declarada por el operador: Organizador de Cables Compacto",
                "Proveedor declarado por el operador: Proveedor MX Alfa",
            ],
            "claim_risk_hints": claim_risk,
            "channel": "Meta",
            "margin_profile": "acceptable",
            "desires": ["Mantener el escritorio ordenado."],
            "differentiators": ["Formato compacto declarado por el operador."],
            "market_context": "Uso domÃ©stico y oficina local en MÃ©xico.",
            "customer_language": ["Quiero dejar de ver cables sueltos."],
            "notes": "PreparaciÃ³n local; revisar antes de usar.",
        }
    )
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_e2e_enrichment_unlocks_full_pack_and_copy_payloads_are_byte_exact(
    tmp_path: Path,
) -> None:
    csv_path = _write_csv(tmp_path / "catalog.csv")
    workspace = tmp_path / "workspace"

    first = rebuild_workspace(csv_path, workspace)
    fixture_id = "a8_r110_cat_001"
    assert first["enrichment_counts"] == {"ABSENT": 1}

    template = create_template(workspace, fixture_id)
    _fill_template(template)

    result = rebuild_workspace(csv_path, workspace)
    candidate_path = workspace / "candidates" / f"{fixture_id}.json"
    fixture = json.loads(candidate_path.read_text(encoding="utf-8"))
    view_model = build_view_model(
        fixture,
        source_fixture=f"catalog.csv#{fixture_id}",
    ).to_dict()

    assert result["enrichment_counts"] == {"ACCEPTED": 1}
    assert view_model["input_richness"]["classification"] == "INPUT_RICH"
    assert view_model["decision"]["methodology"]["status"] == "accepted"
    assert view_model["marketing_pack"]["enabled"] is True
    assert view_model["shopify_pack"]["enabled"] is True
    assert view_model["marketing_pack"]["confidence"]["expert_method_applied"] is True

    document = (workspace / "workspace.html").read_text(encoding="utf-8")
    assert 'data-methodology-present="true"' in document
    assert 'data-role="claim_guard_adjacent" data-adjacent-to="shopify_pack"' in document
    assert 'data-role="claim_guard_adjacent" data-adjacent-to="marketing_pack"' in document

    copy_items = [
        item
        for item in view_model["copy_payloads"]["items"]
        if item["section"] in {"shopify_pack", "marketing_pack"}
    ]
    assert copy_items
    for item in copy_items:
        assert f'data-payload-key="{html.escape(item["key"], quote=True)}"' in document
        assert html.escape(item["text"], quote=True) in document


def test_rebuild_is_byte_identical_for_same_csv_and_enrichment(
    tmp_path: Path,
) -> None:
    csv_path = _write_csv(tmp_path / "catalog.csv")
    workspace = tmp_path / "workspace"
    rebuild_workspace(csv_path, workspace)
    template = create_template(workspace, "a8_r110_cat_001")
    _fill_template(template)

    rebuild_workspace(csv_path, workspace)
    first = {
        "html": _sha(workspace / "workspace.html"),
        "report": _sha(workspace / "intake_report.json"),
        "candidate": _sha(
            workspace / "candidates" / "a8_r110_cat_001.json"
        ),
    }

    rebuild_workspace(csv_path, workspace)
    second = {
        "html": _sha(workspace / "workspace.html"),
        "report": _sha(workspace / "intake_report.json"),
        "candidate": _sha(
            workspace / "candidates" / "a8_r110_cat_001.json"
        ),
    }

    assert second == first


def test_invalid_and_forbidden_enrichment_render_without_crash(
    tmp_path: Path,
) -> None:
    csv_path = _write_csv(tmp_path / "catalog.csv")
    workspace = tmp_path / "workspace"
    rebuild_workspace(csv_path, workspace)

    template = create_template(workspace, "a8_r110_cat_001")
    template.write_text("{", encoding="utf-8")
    result = rebuild_workspace(csv_path, workspace)
    assert result["enrichment_counts"] == {"INVALID_INPUT": 1}
    assert (workspace / "workspace.html").is_file()

    template = create_template(
        workspace,
        "a8_r110_cat_001",
        overwrite=True,
    )
    _fill_template(template)
    payload = json.loads(template.read_text(encoding="utf-8"))
    payload["notes"] = "https://example.com"
    template.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    result = rebuild_workspace(csv_path, workspace)
    assert result["enrichment_counts"] == {"INVALID_INPUT": 1}
    candidate = json.loads(
        (workspace / "candidates" / "a8_r110_cat_001.json").read_text(
            encoding="utf-8"
        )
    )
    assert candidate["decision"]["outcome"] == "INVALID_INPUT"


def test_blocked_methodology_action_is_visible_in_workspace(tmp_path: Path) -> None:
    csv_path = _write_csv(tmp_path / "catalog.csv", category="salud")
    workspace = tmp_path / "workspace"
    rebuild_workspace(csv_path, workspace)
    template = create_template(workspace, "a8_r110_cat_001")
    _fill_template(template, claim_risk="medical")

    payload = json.loads(template.read_text(encoding="utf-8"))
    payload["proof_available"] = [
        "Registro CSV local del operador; no clinical proof"
    ]
    payload["product_facts"] = [
        "Producto declarado por el operador para organizaciÃ³n personal."
    ]
    template.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    result = rebuild_workspace(csv_path, workspace)
    assert result["enrichment_counts"] == {"BLOCKED": 1}

    candidate = json.loads(
        (workspace / "candidates" / "a8_r110_cat_001.json").read_text(
            encoding="utf-8"
        )
    )
    raw_action = candidate["blocked"][0]["operator_actions"][0]["label"]
    view_model = build_view_model(
        candidate,
        source_fixture="catalog.csv#a8_r110_cat_001",
    ).to_dict()
    operator_action = view_model["blocked_queue"][0]["operator_actions"][0]["label"]
    document = (workspace / "workspace.html").read_text(encoding="utf-8")

    assert raw_action.startswith("Operator action:")
    assert html.escape(raw_action, quote=True) not in document
    assert operator_action.startswith("Revisar o reescribir las afirmaciones")
    assert html.escape(operator_action, quote=True) in document
    assert candidate["decision"]["outcome"] == "BLOCKED"
