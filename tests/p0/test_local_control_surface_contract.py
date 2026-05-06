from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "synapse_control_surface.py"
DOC = ROOT / "docs" / "local_control_surface_contract.md"
AGENTS = ROOT / "AGENTS.md"


def load_module():
    spec = importlib.util.spec_from_file_location("synapse_control_surface", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["synapse_control_surface"] = module
    spec.loader.exec_module(module)
    return module


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-S", str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=15,
    )


def test_local_control_surface_catalog_is_guarded() -> None:
    module = load_module()
    catalog = module.build_catalog(python_executable="python")
    errors = module.validate_catalog(catalog)

    assert errors == []
    assert len(catalog) >= 6
    assert len({command.command_id for command in catalog}) == len(catalog)

    for command in catalog:
        assert command.read_only is True
        assert command.requires_secrets is False
        assert command.live_allowed is False
        assert command.writes_repo is False
        assert "--help" in command.argv


def test_local_control_surface_forces_no_live_environment() -> None:
    module = load_module()
    env = module.build_guarded_env({})

    assert env["SYNAPSE_DRY_RUN"] == "1"
    assert env["SYNAPSE_NO_LIVE"] == "1"
    assert env["SYNAPSE_ALLOW_NETWORK"] == "0"
    assert env["SYNAPSE_ALLOW_SPEND"] == "0"
    assert env["SYNAPSE_CONTROL_SURFACE"] == "LOCAL_ONLY"
    assert env["SHOPIFY"] == "PAUSED"


def test_local_control_surface_rejects_unknown_command() -> None:
    module = load_module()
    catalog = module.build_catalog(python_executable="python")

    try:
        module.get_command("rm_rf_everything", catalog)
    except KeyError as exc:
        assert "unknown local control command" in str(exc)
    else:
        raise AssertionError("unknown command was not rejected")


def test_local_control_surface_cli_modes_work_without_sitecustomize() -> None:
    check = run_script("--check")
    assert check.returncode == 0
    assert "LOCAL_CONTROL_SURFACE_OK=1" in check.stdout
    assert "LIVE=0" in check.stdout
    assert "SPEND=0" in check.stdout
    assert "SECRETS=0" in check.stdout
    assert "SHOPIFY=PAUSED" in check.stdout

    listed = run_script("--list")
    assert listed.returncode == 0
    assert "phase1_ready_help" in listed.stdout
    assert "ops_summary_help" in listed.stdout

    json_out = run_script("--json")
    assert json_out.returncode == 0
    payload = json.loads(json_out.stdout)
    assert isinstance(payload, list)
    assert len(payload) >= 6
    assert all(item["live_allowed"] is False for item in payload)
    assert all(item["requires_secrets"] is False for item in payload)


def test_local_control_surface_contract_docs_are_present() -> None:
    doc = DOC.read_text(encoding="utf-8")

    assert "Local Control Surface Contract" in doc
    assert "scripts/synapse_control_surface.py" in doc
    assert "ARBITRARY_SHELL=0" in doc
    assert "SHOPIFY=PAUSED" in doc
    assert "TOKEN_INPUT=0" in doc
    assert "API_WRITE_ACTIONS=0" in doc


def test_local_control_surface_is_referenced_from_agents() -> None:
    agents = AGENTS.read_text(encoding="utf-8")

    assert "docs/local_control_surface_contract.md" in agents
    assert "scripts/synapse_control_surface.py" in agents
    assert "no-live" in agents.lower()
    assert "no-spend" in agents.lower()
    assert "no-secrets" in agents.lower()
