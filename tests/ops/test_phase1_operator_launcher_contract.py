from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "START_SYNAPSE.ps1"
RUNBOOK = ROOT / "docs" / "operator" / "PHASE1_OPERATOR_RUNBOOK.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def test_operator_launcher_is_thin_and_fail_closed() -> None:
    text = _read(LAUNCHER)

    required = (
        "synapse.ui.operator_enrichment_cli",
        "--csv",
        "--workspace",
        "SYNAPSE_SHOPIFY_ENABLED = '0'",
        "SYNAPSE_SHOPIFY_LIVE = '0'",
        "SYNAPSE_DROPI_LIVE = '0'",
        "SYNAPSE_META_LIVE = '0'",
        "SYNAPSE_LIVE_WRITE = '0'",
        "SYNAPSE_DRY_RUN = '1'",
        "NETWORK_AUTHORIZED=false",
        "LIVE_WRITES_AUTHORIZED=false",
        "REAL_SPEND_AUTHORIZED=false",
        "OPERATOR_LAUNCHER=PASS",
        "Restore-SafetyEnvironment",
    )
    for token in required:
        assert token in text

    forbidden = (
        "Invoke-WebRequest",
        "Invoke-RestMethod",
        "curl.exe",
        "wget.exe",
        "http://",
        "https://",
        "git push",
        "--no-verify",
    )
    for token in forbidden:
        assert token not in text


def test_operator_runbook_records_phase1_freeze_and_boundaries() -> None:
    text = _read(RUNBOOK)

    required = (
        "Construction freeze",
        "P0/P1",
        r".\START_SYNAPSE.ps1 -Csv .\catalogo.csv",
        "decision.permission_gate=REVIEW",
        "live Shopify",
        "live Dropi",
        "live Meta",
        "real ad spend",
        "INPUT_RICH",
    )
    for token in required:
        assert token in text


@pytest.mark.skipif(
    os.name != "nt",
    reason="Phase 1 launcher is intentionally a Windows PowerShell operator surface",
)
def test_operator_launcher_executes_existing_local_flow(tmp_path: Path) -> None:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell executable unavailable")

    csv_path = tmp_path / "catalog.csv"
    csv_path.write_text(
        "product_id,title,supplier,category,supplier_price_mxn,"
        "shipping_cost_mxn,sale_price_mxn,payment_fee_mxn,source_url,notes\n"
        "op_001,Producto Operador,Proveedor Local,hogar,"
        "100.00,50.00,299.00,10.00,,\n",
        encoding="utf-8",
        newline="\n",
    )

    workspace = tmp_path / "workspace"

    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

    completed = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(LAUNCHER),
            "-Csv",
            str(csv_path),
            "-Workspace",
            str(workspace),
            "-NoOpen",
        ],
        cwd=ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
        text=True,
        timeout=90,
        check=False,
    )


    assert completed.returncode == 0

    html_path = workspace / "workspace.html"
    report_path = workspace / "intake_report.json"

    assert html_path.is_file()
    assert report_path.is_file()

    html = html_path.read_text(encoding="utf-8")
    assert "http://" not in html
    assert "https://" not in html
