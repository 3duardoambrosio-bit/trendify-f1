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

def test_a8_r54l_legal_avoidance_hook_sets_fear_appeal(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    evidence_root = tmp_path / "legal_avoidance"

    result = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "synapse.cli",
            "simulate",
            "--evidence-root",
            str(evidence_root),
            "--product",
            "Organizador inteligente para documentos del auto",
            "--category",
            "Auto",
            "--market",
            "MX",
            "--price",
            "349",
            "--cost",
            "95",
            "--traffic",
            "650",
            "--days",
            "7",
            "--marketing-angle",
            "Producto preventivo para conductores que olvidan documentos o accesorios de emergencia.",
            "--primary-hook",
            "Evita multas y problemas legales por olvidar documentos del auto antes de salir",
            "--target-audience",
            "Conductores urbanos que usan el auto todos los días",
            "--use-case",
            "Tener papeles, licencia y accesorios esenciales en un solo lugar",
        ],
        cwd=repo,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=90,
    )

    assert result.returncode == 0, result.stdout[-4000:]

    candidates = [
        path
        for path in evidence_root.iterdir()
        if path.is_dir() and (path / "safety_posture.json").exists()
    ]

    assert candidates, result.stdout[-4000:]

    latest = max(candidates, key=lambda path: path.stat().st_mtime)
    safety = json.loads((latest / "safety_posture.json").read_text(encoding="utf-8"))
    categories = set(safety.get("claim_safety_categories", []))

    assert "LEGAL" in categories
    assert "FEAR_APPEAL" in categories
    assert safety.get("external_mutation") in (0, False, None)
    assert safety.get("spend_count") in (0, False, None)
    assert safety.get("shopify_write_count") in (0, False, None)
    assert safety.get("meta_write_count") in (0, False, None)
    assert safety.get("dropi_write_count") in (0, False, None)

