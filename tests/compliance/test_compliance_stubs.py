# V3GAP:E-01_aviso_privacidad_mx
# V3GAP:F-01_profeco_complete
# V3GAP:F-03_nom_verification_flag
# V3GAP:creative_review_no_prohibited_claims
# V3GAP:G-01_order_status_auto_reply
# V3GAP:oxxo_reminder_day3
# V3GAP:cod_pre_confirmation
"""Tests for compliance and external gate stubs. Estandar F1."""
from __future__ import annotations
from dataclasses import FrozenInstanceError
from synapse.compliance.mx_prelaunch import (
    MX_PRELAUNCH_CHECKLIST, get_pending_items, get_checklist_ids,
    AVISO_PRIVACIDAD, PROFECO_COMPLETE, NOM_VERIFICATION, CREATIVE_REVIEW,
)
from synapse.compliance.external_gates import (
    EXTERNAL_GATES, get_post_launch_gates, get_gate_ids,
    ORDER_STATUS_AUTO_REPLY, OXXO_REMINDER_DAY3, COD_PRE_CONFIRMATION,
)

def test_checklist_has_exactly_4_items():
    assert len(MX_PRELAUNCH_CHECKLIST) == 4

def test_all_items_require_manual_verification():
    for item in MX_PRELAUNCH_CHECKLIST:
        assert item.requires_manual_verification is True, item.item_id

def test_no_items_are_code_features():
    for item in MX_PRELAUNCH_CHECKLIST:
        assert item.is_code_feature is False, item.item_id

def test_aviso_privacidad_references_anticorrupcion():
    assert "anticorrupcion" in AVISO_PRIVACIDAD.description.lower()

def test_aviso_privacidad_references_arco():
    assert "ARCO" in AVISO_PRIVACIDAD.description.upper()

def test_profeco_references_art56():
    assert "56" in PROFECO_COMPLETE.description

def test_profeco_references_5_dias():
    assert "5 dias" in PROFECO_COMPLETE.description

def test_profeco_references_art77():
    assert "77" in PROFECO_COMPLETE.description

def test_checklist_ids_complete():
    ids = get_checklist_ids()
    assert "E-01_aviso_privacidad_mx" in ids
    assert "F-01_profeco_complete" in ids
    assert "F-03_nom_verification_flag" in ids
    assert "creative_review_no_prohibited_claims" in ids
    assert len(ids) == 4

def test_pending_items_returns_all():
    assert len(get_pending_items()) == 4

def test_compliance_items_are_frozen():
    try:
        AVISO_PRIVACIDAD.description = "hacked"
        assert False, "Should be frozen"
    except (FrozenInstanceError, AttributeError):
        pass

def test_external_gates_has_exactly_3():
    assert len(EXTERNAL_GATES) == 3

def test_all_external_gates_are_post_launch():
    for gate in EXTERNAL_GATES:
        assert gate.phase == "post_launch", gate.gate_id

def test_no_external_gates_are_implemented():
    for gate in EXTERNAL_GATES:
        assert gate.is_implemented is False, gate.gate_id

def test_order_status_uses_whatsapp():
    assert ORDER_STATUS_AUTO_REPLY.channel == "whatsapp"

def test_oxxo_reminder_channel():
    assert "whatsapp" in OXXO_REMINDER_DAY3.channel or "sms" in OXXO_REMINDER_DAY3.channel

def test_cod_pre_confirmation_channel():
    assert "whatsapp" in COD_PRE_CONFIRMATION.channel or "sms" in COD_PRE_CONFIRMATION.channel

def test_gate_ids_complete():
    ids = get_gate_ids()
    assert "G-01_order_status_auto_reply" in ids
    assert "oxxo_reminder_day3" in ids
    assert "cod_pre_confirmation" in ids
    assert len(ids) == 3

def test_external_gates_are_frozen():
    try:
        ORDER_STATUS_AUTO_REPLY.channel = "hacked"
        assert False, "Should be frozen"
    except (FrozenInstanceError, AttributeError):
        pass