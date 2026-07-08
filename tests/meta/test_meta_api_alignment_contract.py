from __future__ import annotations

import re
from pathlib import Path

import pytest

from synapse.meta.graph_version import DEFAULT_META_GRAPH_VERSION, resolve_meta_graph_version


ROOT = Path(__file__).resolve().parents[2]

WRITE_PATH_FILES = [
    "synapse/meta_publish_execute.py",
    "synapse/meta_publish_plan.py",
    "synapse/meta_publish_preflight.py",
    "synapse/meta/publisher_adapter.py",
    "synapse/meta/safe_client.py",
    "synapse/meta/meta_payloads.py",
]

LEGACY_TARGETING_FILES = [
    "synapse/ads/ads_intelligence.py",
    "synapse/marketing_os/campaign_blueprint.py",
]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_publisher_adapter_has_no_local_graph_version_constant() -> None:
    assert "_DEFAULT_GRAPH_VERSION" not in _read("synapse/meta/publisher_adapter.py")


def test_meta_graph_version_default_is_v25(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("META_GRAPH_VERSION", raising=False)

    assert DEFAULT_META_GRAPH_VERSION == "v25.0"
    assert resolve_meta_graph_version() == "v25.0"


def test_meta_graph_version_explicit_override_is_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_GRAPH_VERSION", "v25.0")

    assert resolve_meta_graph_version() == "v25.0"
    assert resolve_meta_graph_version("v99.0") == "v99.0"


def test_meta_write_path_has_no_v22_fallback_or_instagram_actor_id() -> None:
    combined = "\n".join(_read(rel) for rel in WRITE_PATH_FILES)

    assert "v22.0" not in combined
    assert "instagram_actor_id" not in combined
    assert "instagram_user_id" in _read("synapse/meta_publish_plan.py")


def test_legacy_detailed_targeting_modules_do_not_feed_meta_write_path() -> None:
    write_path_combined = "\n".join(_read(rel) for rel in WRITE_PATH_FILES)
    legacy_combined = "\n".join(_read(rel) for rel in LEGACY_TARGETING_FILES)

    assert re.search(r"\b(interests|exclusions|Interest Based|detailed_targeting)\b", legacy_combined)

    assert not re.search(
        r"^\s*(from|import)\s+.*(ads_intelligence|campaign_blueprint|synapse\.ads|synapse\.marketing_os|TargetingConfig)",
        write_path_combined,
        flags=re.MULTILINE,
    )
    assert not re.search(
        r"^\s*(from|import)\s+.*(synapse\.meta|meta_publish|publisher_adapter|safe_client|meta_payloads)",
        legacy_combined,
        flags=re.MULTILINE,
    )


def test_meta_write_guards_remain_paused_no_live_and_ledger_safe() -> None:
    safe_client = _read("synapse/meta/safe_client.py")
    publisher = _read("synapse/meta/publisher_adapter.py")
    execute = _read("synapse/meta_publish_execute.py")

    assert 'payload["status"] = "PAUSED"' in safe_client
    assert '"status": "PAUSED"' in safe_client
    assert "SYNAPSE_META_LIVE" in publisher
    assert "SYNAPSE_FLAG_META_LIVE_API" not in publisher
    assert "Default/off mode stays mock/compat" in publisher
    assert "--ledger-disable is forbidden in --mode live" in execute
