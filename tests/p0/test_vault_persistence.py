from __future__ import annotations

import json
import logging
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


# --- 1. Write state, restart, read state correctly ---


def test_write_then_reload_preserves_spent(tmp_path: Path) -> None:
    """After request_spend (Ok), state is persisted; a new Vault loads it back."""
    v1 = _mk_vault(tmp_path, state=True)
    sf = tmp_path / "vault_state.json"

    r = v1.request_spend(Decimal("10.00"), "learning")
    assert r.is_ok()
    assert sf.exists()

    # Verify JSON uses string decimals
    payload = json.loads(sf.read_text(encoding="utf-8"))
    assert payload["spent"]["learning_spent"] == "10.00"
    assert payload["spent"]["operational_spent"] == "0"

    # Reload into a new Vault
    v2 = _mk_vault(tmp_path, state=True)
    assert v2.learning_spent == Decimal("10.00")
    assert v2.operational_spent == Decimal("0")
    assert v2.learning_remaining == Decimal("20.00")


def test_operational_spend_persists(tmp_path: Path) -> None:
    v1 = _mk_vault(tmp_path, state=True)
    v1.request_spend(Decimal("5.50"), "operational")

    v2 = _mk_vault(tmp_path, state=True)
    assert v2.operational_spent == Decimal("5.50")
    assert v2.learning_spent == Decimal("0")


def test_multiple_spends_accumulate_across_restarts(tmp_path: Path) -> None:
    v1 = _mk_vault(tmp_path, state=True)
    v1.request_spend(Decimal("3.00"), "learning")
    v1.request_spend(Decimal("7.00"), "operational")

    v2 = _mk_vault(tmp_path, state=True)
    assert v2.learning_spent == Decimal("3.00")
    assert v2.operational_spent == Decimal("7.00")

    v2.request_spend(Decimal("2.00"), "learning")

    v3 = _mk_vault(tmp_path, state=True)
    assert v3.learning_spent == Decimal("5.00")
    assert v3.operational_spent == Decimal("7.00")


# --- 2. Corrupt file → WARNING + defaults ---


def test_corrupt_file_logs_warning_and_starts_fresh(tmp_path: Path, caplog) -> None:
    sf = tmp_path / "vault_state.json"
    sf.write_text("{{{INVALID JSON", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="vault.vault"):
        v = Vault(
            total_budget=Decimal("100.00"),
            learning_budget=Decimal("30.00"),
            operational_budget=Decimal("55.00"),
            reserve_budget=Decimal("15.00"),
            state_file=sf,
        )

    assert v.learning_spent == Decimal("0")
    assert v.operational_spent == Decimal("0")
    assert any("VAULT_STATE_CORRUPTED" in msg for msg in caplog.messages)


def test_empty_file_logs_warning_and_starts_fresh(tmp_path: Path, caplog) -> None:
    sf = tmp_path / "vault_state.json"
    sf.write_text("", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="vault.vault"):
        v = Vault(
            total_budget=Decimal("100.00"),
            learning_budget=Decimal("30.00"),
            operational_budget=Decimal("55.00"),
            reserve_budget=Decimal("15.00"),
            state_file=sf,
        )

    assert v.learning_spent == Decimal("0")
    assert v.operational_spent == Decimal("0")


def test_bad_schema_logs_warning_and_starts_fresh(tmp_path: Path, caplog) -> None:
    sf = tmp_path / "vault_state.json"
    sf.write_text(json.dumps({"schema": "unknown_v99"}), encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="vault.vault"):
        v = Vault(
            total_budget=Decimal("100.00"),
            learning_budget=Decimal("30.00"),
            operational_budget=Decimal("55.00"),
            reserve_budget=Decimal("15.00"),
            state_file=sf,
        )

    assert v.learning_spent == Decimal("0")
    assert v.operational_spent == Decimal("0")
    assert any("VAULT_STATE_UNSUPPORTED_SCHEMA" in msg for msg in caplog.messages)


# --- 3. Missing file → defaults (no error) ---


def test_missing_file_starts_with_defaults(tmp_path: Path) -> None:
    sf = tmp_path / "vault_state.json"
    assert not sf.exists()

    v = Vault(
        total_budget=Decimal("100.00"),
        learning_budget=Decimal("30.00"),
        operational_budget=Decimal("55.00"),
        reserve_budget=Decimal("15.00"),
        state_file=sf,
    )

    assert v.learning_spent == Decimal("0")
    assert v.operational_spent == Decimal("0")


# --- 4. Decimal serialization fidelity ---


def test_decimal_precision_preserved(tmp_path: Path) -> None:
    v1 = _mk_vault(tmp_path, state=True)
    v1.request_spend(Decimal("0.01"), "learning")

    payload = json.loads((tmp_path / "vault_state.json").read_text(encoding="utf-8"))
    assert payload["spent"]["learning_spent"] == "0.01"
    assert isinstance(payload["spent"]["learning_spent"], str)

    v2 = _mk_vault(tmp_path, state=True)
    assert v2.learning_spent == Decimal("0.01")
