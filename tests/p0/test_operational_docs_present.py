from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKLIST = ROOT / "docs" / "operational_readiness_checklist.md"
GO_NO_GO = ROOT / "docs" / "go_no_go_template.md"
AGENTS = ROOT / "AGENTS.md"


def read(path: Path) -> str:
    assert path.exists(), f"missing required file: {path}"
    return path.read_text(encoding="utf-8")


def test_operational_readiness_checklist_exists_and_has_required_gates() -> None:
    text = read(CHECKLIST)

    assert "Operational Readiness Checklist" in text
    assert "no live API" in text
    assert "no real ad spend" in text
    assert "real secrets pasted in chat/docs: 0" in text
    assert "tests/p0/test_kill_switch_e2e_v1.py PASS" in text
    assert "documented manual procedure alone is insufficient" in text

    required_items = [
        "Facebook Business Page",
        "Instagram Business",
        "Meta Business Manager",
        "Shopify store",
        "Shopify Custom App",
        "Webhook secret",
        "Dropi",
        "First SKU",
        "Creative assets",
        "capital cap",
        "Kill switch",
        "Monitoring runbook",
        "Customer support",
        "Refund",
        "Final human go/no-go",
    ]

    for item in required_items:
        assert item in text

    assert text.count("| human |") >= 8
    assert text.count("| system |") >= 3
    assert text.count("| yes |") >= 15
    assert text.count("no-check") >= 15


def test_go_no_go_template_exists_and_has_numeric_decision_fields() -> None:
    text = read(GO_NO_GO)

    required_fields = [
        "Date",
        "HEAD",
        "PC_READY_SCORE",
        "Capital reserved",
        "Capital allowed to risk",
        "Daily spend cap",
        "Campaign spend cap",
        "Stop-loss amount",
        "Stop-loss condition",
        "First SKU",
        "Human signature",
        "Signature timestamp",
        "GO valid until",
        "Template HEAD at signature",
        "GO",
        "NO-GO",
        "HOLD",
        "PATCH FIRST",
    ]

    for field in required_fields:
        assert field in text

    assert "Decision owner | human" in text
    assert "no real secrets" in text
    assert "A GO is invalid unless" in text
    assert "GO validity is at most 72 hours from signature" in text
    assert "kill switch is verified by executable evidence" in text
    assert text.count("TODO") >= 20


def test_agents_references_operational_readiness_docs() -> None:
    text = read(AGENTS)

    assert "operational_readiness_checklist.md" in text
    assert "go_no_go_template.md" in text
