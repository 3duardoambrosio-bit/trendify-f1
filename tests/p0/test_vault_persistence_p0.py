from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from vault.vault import Vault


def _mk_vault(tmp_path: Path, *, state: bool) -> Vault:
    sf = (tmp_path / "vault_state.json") if state else None
    return Vault(
        total_budget=Decimal("100.00"),
        learning_budget=Decimal("30.00"),
        operational_budget=Decimal("55.00"),
        reserve_budget=Decimal("15.00"),
        state_file=sf,
    )


def test_vault_persistence_roundtrip(tmp_path: Path) -> None:
    v1 = _mk_vault(tmp_path, state=True)
    sf = tmp_path / "vault_state.json"
    assert sf.exists() is False

    r1 = v1.request_spend(Decimal("10.00"), "learning")
    assert r1.is_ok() is True
    assert sf.exists() is True

    payload = json.loads(sf.read_text(encoding="utf-8"))
    assert payload["schema"] == "vault_state_v1"
    assert Decimal(payload["spent"]["learning_spent"]) == Decimal("10.00")
    assert Decimal(payload["spent"]["operational_spent"]) == Decimal("0")

    v2 = _mk_vault(tmp_path, state=True)
    assert v2.learning_spent == Decimal("10.00")
    assert v2.operational_spent == Decimal("0")
    assert v2.learning_remaining == Decimal("20.00")

    r2 = v2.request_spend(Decimal("25.00"), "learning")
    assert r2.is_err() is True

    r3 = v2.request_spend(Decimal("20.00"), "learning")
    assert r3.is_ok() is True
    payload2 = json.loads(sf.read_text(encoding="utf-8"))
    assert Decimal(payload2["spent"]["learning_spent"]) == Decimal("30.00")


def test_vault_persistence_config_mismatch_warns_and_defaults(tmp_path: Path) -> None:
    v1 = _mk_vault(tmp_path, state=True)
    _ = v1.request_spend(Decimal("1.00"), "learning")
    sf = tmp_path / "vault_state.json"
    assert sf.exists() is True

    # Config mismatch => WARNING + start with defaults (0)
    v2 = Vault(
        total_budget=Decimal("200.00"),  # mismatch intencional
        learning_budget=Decimal("60.00"),
        operational_budget=Decimal("110.00"),
        reserve_budget=Decimal("30.00"),
        state_file=sf,
    )
    assert v2.learning_spent == Decimal("0")
    assert v2.operational_spent == Decimal("0")


def test_vault_persistence_corrupt_state_warns_and_defaults(tmp_path: Path) -> None:
    sf = tmp_path / "vault_state.json"
    sf.write_text("NOT VALID JSON {{{", encoding="utf-8")

    # Corrupt file => WARNING + start with defaults (0)
    v = Vault(
        total_budget=Decimal("100.00"),
        learning_budget=Decimal("30.00"),
        operational_budget=Decimal("55.00"),
        reserve_budget=Decimal("15.00"),
        state_file=sf,
    )
    assert v.learning_spent == Decimal("0")
    assert v.operational_spent == Decimal("0")
def test_vault_env_state_file_roundtrip(tmp_path: Path, monkeypatch) -> None:
    sf = tmp_path / "vault_env_state.json"
    monkeypatch.setenv("SYNAPSE_VAULT_STATE_FILE", str(sf))

    v = Vault(
        total_budget=Decimal("100.00"),
        learning_budget=Decimal("30.00"),
        operational_budget=Decimal("55.00"),
        reserve_budget=Decimal("15.00"),
        # state_file OMITIDO a propósito: debe venir por ENV
    )
    assert sf.exists() is False

    r = v.request_spend(Decimal("2.00"), "learning")
    assert r.is_ok() is True
    assert sf.exists() is True

    v2 = Vault(
        total_budget=Decimal("100.00"),
        learning_budget=Decimal("30.00"),
        operational_budget=Decimal("55.00"),
        reserve_budget=Decimal("15.00"),
    )
    assert v2.learning_spent == Decimal("2.00")
