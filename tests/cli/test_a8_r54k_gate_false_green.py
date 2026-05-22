import json
import re
import subprocess
import sys
from pathlib import Path


def _run_simulate(tmp_path: Path, primary_hook: str) -> tuple[str, Path]:
    evidence_root = tmp_path / "evidence"
    cmd = [
        sys.executable,
        "-X",
        "utf8",
        "-m",
        "synapse.cli",
        "simulate",
        "--evidence-root",
        str(evidence_root),
        "--product",
        "Producto Test A8 R54K",
        "--category",
        "Testing",
        "--market",
        "MX",
        "--price",
        "999",
        "--cost",
        "300",
        "--traffic",
        "700",
        "--days",
        "7",
        "--marketing-angle",
        "Producto de prueba para validar gates adversariales.",
        "--primary-hook",
        primary_hook,
        "--target-audience",
        "Operadores de prueba",
        "--use-case",
        "Validar gates de creatividad y claim safety.",
    ]
    completed = subprocess.run(
        cmd,
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )
    evidence_dirs = [
        path
        for path in evidence_root.iterdir()
        if path.is_dir() and (path / "safety_posture.json").exists()
    ]
    assert evidence_dirs, completed.stdout
    evidence_dir = max(evidence_dirs, key=lambda path: path.stat().st_mtime)
    return completed.stdout, evidence_dir


def test_a8_r54k_dile_adios_counts_as_generic_phrase(tmp_path: Path) -> None:
    stdout, _ = _run_simulate(
        tmp_path,
        "Dile adiós a la frustración con Producto Test A8 R54K",
    )

    match = re.search(r"GENERIC_PHRASE_COUNT=(\d+)", stdout)
    assert match is not None, stdout
    assert int(match.group(1)) >= 1, stdout


def test_a8_r54k_claim_safety_categories_detect_performance_time_promise(tmp_path: Path) -> None:
    _, evidence_dir = _run_simulate(
        tmp_path,
        "Recupera enfoque en 15 minutos con Producto Test A8 R54K",
    )

    safety = json.loads((evidence_dir / "safety_posture.json").read_text(encoding="utf-8"))
    categories = set(safety.get("claim_safety_categories", []))

    assert "PERFORMANCE" in categories, safety
    assert "SPECIFIC_TIME_PROMISE" in categories, safety
