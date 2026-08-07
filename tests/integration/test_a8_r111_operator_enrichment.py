from __future__ import annotations

import json
from pathlib import Path

from synapse.integration.operator_enrichment import (
    STATUS_ABSENT,
    STATUS_BLOCKED,
    STATUS_INVALID,
    STATUS_PARTIAL,
    apply_enrichment_file,
    build_enrichment_template,
)
from synapse.ui.local_catalog_workspace import parse_catalog_csv


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


def _fixture(tmp_path: Path, *, category: str = "hogar_y_oficina") -> dict:
    result = parse_catalog_csv(_write_csv(tmp_path / "catalog.csv", category=category))
    return dict(result.fixtures[0])


def _rich_payload(fixture_id: str, *, claim_risk: str = "low") -> dict:
    payload = build_enrichment_template(fixture_id)
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
    return payload


def test_template_never_prefills_operator_content() -> None:
    payload = build_enrichment_template("a8_r110_cat_001")
    assert payload["channel"] == "Meta"
    assert payload["buyer_pain"] == ""
    assert payload["buyer_state"] == ""
    assert payload["objections"] == []
    assert payload["proof_available"] == []
    assert payload["product_facts"] == []
    assert payload["target_audience"] == ""
    assert payload["_help"]["buyer_pain"]


def test_absent_partial_invalid_json_and_forbidden_are_honest(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    fixture_id = str(fixture["fixture_id"])

    absent = apply_enrichment_file(fixture, None)
    assert absent.status == STATUS_ABSENT
    assert absent.fixture["decision"]["outcome"] == "EVALUATING"
    assert "marketing" not in absent.fixture
    assert "shopify" not in absent.fixture

    partial_path = tmp_path / "partial.json"
    partial = build_enrichment_template(fixture_id)
    partial.update(
        {
            "buyer_pain": "Cables sueltos.",
            "target_audience": "Personas con escritorio.",
            "objections": ["No sÃ© si cabe."],
            "desires": ["Orden."],
        }
    )
    partial_path.write_text(
        json.dumps(partial, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    partial_result = apply_enrichment_file(fixture, partial_path)
    assert partial_result.status == STATUS_PARTIAL
    assert partial_result.richness == "INPUT_PARTIAL"
    assert "marketing" not in partial_result.fixture
    assert "shopify" not in partial_result.fixture
    assert partial_result.missing_fields

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{", encoding="utf-8")
    invalid_result = apply_enrichment_file(fixture, invalid_path)
    assert invalid_result.status == STATUS_INVALID
    assert invalid_result.fixture["decision"]["outcome"] == "INVALID_INPUT"
    assert invalid_result.errors == ("invalid_enrichment_json",)

    forbidden_path = tmp_path / "forbidden.json"
    forbidden = _rich_payload(fixture_id)
    forbidden["notes"] = "ver https://example.com"
    forbidden_path.write_text(
        json.dumps(forbidden, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    forbidden_result = apply_enrichment_file(fixture, forbidden_path)
    assert forbidden_result.status == STATUS_INVALID
    assert forbidden_result.fixture["decision"]["outcome"] == "INVALID_INPUT"
    assert "forbidden_tokens_in_fields=" in forbidden_result.errors[0]


def test_high_claim_risk_routes_exact_engine_output_to_blocked_queue(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, category="salud")
    fixture_id = str(fixture["fixture_id"])
    payload = _rich_payload(fixture_id, claim_risk="medical")
    payload["product_facts"] = [
        "Producto declarado por el operador para organizaciÃ³n personal."
    ]
    payload["proof_available"] = [
        "Registro CSV local del operador; no clinical proof"
    ]

    path = tmp_path / "blocked.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )

    result = apply_enrichment_file(fixture, path)

    assert result.status == STATUS_BLOCKED
    assert result.methodology_status == "blocked"
    assert result.fixture["decision"]["outcome"] == "BLOCKED"
    assert "marketing" not in result.fixture
    assert "shopify" not in result.fixture

    methodology = result.fixture["decision"]["methodology"]
    blocked_item = result.fixture["blocked"][0]
    action = blocked_item["operator_actions"][0]

    assert blocked_item["reason"]
    assert blocked_item["reason"] in methodology["safe_output"]
    assert action["label"].startswith("Operator action:")
    assert action["label"] in methodology["safe_output"]
    assert action["notes"] == methodology["safe_output"]
