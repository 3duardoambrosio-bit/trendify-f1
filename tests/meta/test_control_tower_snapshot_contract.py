# tests/meta/test_control_tower_snapshot_contract.py
import json
import subprocess
import sys
from pathlib import Path


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def test_control_tower_snapshot_contract(tmp_path: Path):
    """
    Contract test (SSOT):
    - Genera inputs mínimos en data/run/
    - Ejecuta snapshot builder
    - Verifica schema + KPIs críticos
    """
    repo = tmp_path
    run_dir = repo / "data" / "run"

    # Inputs mínimos que el snapshot debería poder consumir
    _write_json(run_dir / "meta_publish_run.json", {
        "mode": "simulate",
        "counts": {"results": 13, "errors": 0, "steps": 13},
        "files": {"count": 3, "missing": 0, "overall_sha12": "7b5b43872870"},
        "run_fingerprint_12": "a46df2b8960a",
        "marker": "TEST_RUN",
        "status": "OK",
        "ts": "2026-01-01T00:00:00Z",
    })

    _write_json(run_dir / "meta_publish_report.json", {
        "mode": "simulate",
        "exec": {"rows": 13, "errors": 0},
        "status": "OK",
        "marker": "TEST_REPORT",
        "ts": "2026-01-01T00:00:00Z",
    })

    _write_json(run_dir / "meta_policy_check.json", {
        "mode": "simulate",
        "status": "OK",
        "marker": "TEST_POLICY",
        "ts": "2026-01-01T00:00:00Z",
    })

    _write_json(run_dir / "meta_autopilot.json", {
        "status": "GREEN",
        "health": {"status": "GREEN"},
        "marker": "TEST_AUTOPILOT",
        "ts": "2026-01-01T00:00:00Z",
    })

    _write_json(run_dir / "meta_publish_runs_index.json", {
        "count": 25,
        "latest_ts": "2026-01-01T00:00:00Z",
        "marker": "TEST_INDEX",
        "runs": [],
        "runs_dir": str(run_dir / "meta_publish_runs"),
    })

    out_path = run_dir / "control_tower_snapshot.json"

    # Ejecuta builder (módulo “largo”)
    cmd = [
        sys.executable,
        "-m",
        "synapse.meta.meta_control_tower_snapshot",
        "--repo",
        str(repo),
        "--out",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    assert proc.returncode == 0, f"snapshot builder failed\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert out_path.exists(), "snapshot output no fue generado"

    snap = json.loads(out_path.read_text(encoding="utf-8"))

    # Top-level keys (contract mínimo)
    for k in ["kpis", "marker", "paths", "raw", "repo_root", "ts"]:
        assert k in snap, f"snapshot missing key: {k}"

    kpis = snap["kpis"]
    for k in [
        "mode", "policy_status", "autopilot_health", "runs_count",
        "rows", "errors", "files_count", "missing_count", "fp12", "sha12"
    ]:
        assert k in kpis, f"kpis missing key: {k}"

    # KPIs críticos (no “—”, no strings raras)
    assert kpis["mode"] == "simulate"
    assert kpis["policy_status"] == "OK"
    assert kpis["autopilot_health"] == "GREEN"
    assert int(kpis["runs_count"]) == 25
    assert int(kpis["rows"]) == 13
    assert int(kpis["errors"]) == 0
    assert int(kpis["files_count"]) == 3
    assert int(kpis["missing_count"]) == 0
    assert kpis["fp12"] == "a46df2b8960a"
    assert kpis["sha12"] == "7b5b43872870"
