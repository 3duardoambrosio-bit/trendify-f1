"""
Doctor CLI - Health checks para SYNAPSE.

Uso:
    python -m synapse.infra.doctor

Output:
    GREEN: Todo OK
    YELLOW: Warnings (puede operar)
    RED: Errores críticos (no operar)
"""

from __future__ import annotations

import json
import sys
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Literal, Optional, Tuple
import importlib
import logging
logger = logging.getLogger(__name__)


# ============================================================
# TYPES
# ============================================================

Status = Literal["GREEN", "YELLOW", "RED"]


@dataclass
class CheckResult:
    """Resultado de un check."""
    name: str
    status: Status
    message: str
    detail: Optional[str] = None


# ============================================================
# MODE SWITCHES
# ============================================================

def _is_ci_or_test() -> bool:
    """
    En tests/CI/bootstraps no debemos marcar RED por falta de data de pipeline.
    Esto desbloquea repos limpios + test suites.
    """
    return (
        os.getenv("PYTEST_CURRENT_TEST") is not None
        or os.getenv("CI") in ("1", "true", "TRUE")
        or os.getenv("SYNAPSE_BOOTSTRAP") in ("1", "true", "TRUE")
        or os.getenv("SYNAPSE_RELAX_DOCTOR") in ("1", "true", "TRUE")
    )


def _data_missing_status() -> Status:
    # En test/CI => warning. En operación real => RED.
    return "YELLOW" if _is_ci_or_test() else "RED"


# ============================================================
# CHECK FUNCTIONS
# ============================================================

def check_pack_exists() -> CheckResult:
    """Verifica que el pack Dropi existe."""
    pack_path = Path("data/evidence/launch_candidates_dropi_dump_f1_v2.json")

    if not pack_path.exists():
        return CheckResult("pack_exists", _data_missing_status(), "Pack no encontrado", str(pack_path))

    try:
        data = json.loads(pack_path.read_text(encoding="utf-8"))
        if data.get("isSuccess") != True:
            return CheckResult("pack_exists", "RED", "Pack inválido (isSuccess != true)")

        top = data.get("top", [])
        if len(top) < 1:
            return CheckResult("pack_exists", "RED", "Pack vacío (top.length = 0)")

        return CheckResult("pack_exists", "GREEN", f"Pack OK ({len(top)} productos)")

    except json.JSONDecodeError as e:
        return CheckResult("pack_exists", "RED", "Pack no es JSON válido", str(e))
    except Exception as e:
        return CheckResult("pack_exists", "RED", "Error leyendo pack", str(e))


def check_canonical_csv() -> CheckResult:
    """Verifica que el CSV canónico existe y tiene datos."""
    csv_path = Path("data/catalog/candidates_real.csv")

    if not csv_path.exists():
        return CheckResult("canonical_csv", _data_missing_status(), "CSV canónico no encontrado", str(csv_path))

    try:
        content = csv_path.read_text(encoding="utf-8")
        lines = [l for l in content.strip().split("\n") if l.strip()]

        if len(lines) < 2:  # Header + at least 1 row
            return CheckResult("canonical_csv", "RED", "CSV vacío o solo header")

        # Check for NaN titles
        if "nan" in content.lower():
            return CheckResult("canonical_csv", "YELLOW", f"CSV tiene {content.lower().count('nan')} NaN values")

        return CheckResult("canonical_csv", "GREEN", f"CSV OK ({len(lines) - 1} rows)")

    except Exception as e:
        return CheckResult("canonical_csv", "RED", "Error leyendo CSV", str(e))


def check_evidence_fanout() -> CheckResult:
    """Verifica que evidence/products tiene archivos."""
    evidence_path = Path("data/evidence/products")

    if not evidence_path.exists():
        return CheckResult("evidence_fanout", _data_missing_status(), "Carpeta evidence/products no existe")

    json_files = list(evidence_path.glob("*.json"))

    if len(json_files) < 1:
        return CheckResult("evidence_fanout", _data_missing_status(), "Sin archivos JSON en evidence/products")

    # Verify at least one is valid JSON
    valid = 0
    for f in json_files[:5]:  # Check first 5
        try:
            json.loads(f.read_text(encoding="utf-8"))
            valid += 1
        except Exception as e:
            logger.debug("suppressed exception", exc_info=True)

    if valid == 0:
        return CheckResult("evidence_fanout", "RED", "Ningún JSON válido en evidence/products")

    return CheckResult("evidence_fanout", "GREEN", f"Evidence OK ({len(json_files)} archivos)")


def check_shortlist() -> CheckResult:
    """Verifica que shortlist existe."""
    shortlist_path = Path("data/launch/shortlist_dropi_f1.csv")

    if not shortlist_path.exists():
        return CheckResult("shortlist", "YELLOW", "Shortlist no encontrado (opcional)")

    try:
        content = shortlist_path.read_text(encoding="utf-8")
        lines = [l for l in content.strip().split("\n") if l.strip()]
        return CheckResult("shortlist", "GREEN", f"Shortlist OK ({len(lines) - 1} productos)")
    except Exception as e:
        return CheckResult("shortlist", "YELLOW", "Error leyendo shortlist", str(e))


def check_pytest_config() -> CheckResult:
    """Verifica que pytest.ini existe."""
    pytest_ini = Path("pytest.ini")

    if not pytest_ini.exists():
        return CheckResult("pytest_config", "YELLOW", "pytest.ini no encontrado (usar --import-mode=prepend)")

    content = pytest_ini.read_text(encoding="utf-8", errors="ignore")
    if "import-mode=prepend" not in content and "import_mode=prepend" not in content:
        return CheckResult("pytest_config", "YELLOW", "pytest.ini sin import-mode=prepend")

    return CheckResult("pytest_config", "GREEN", "pytest.ini OK")


def check_imports_core() -> CheckResult:
    """Verifica imports de módulos core."""
    modules_to_check = [
        ("synapse", "synapse"),
        ("synapse.marketing_os", "marketing_os"),
    ]

    failed = []
    for import_name, display_name in modules_to_check:
        try:
            importlib.import_module(import_name)
        except ImportError as e:
            failed.append(f"{display_name}: {e}")

    if failed:
        return CheckResult("imports_core", "RED", f"Imports fallidos: {len(failed)}", "; ".join(failed))

    return CheckResult("imports_core", "GREEN", f"Imports OK ({len(modules_to_check)} módulos)")


def check_imports_marketing_os() -> CheckResult:
    """Verifica imports específicos de Marketing OS."""
    try:
        from synapse.marketing_os import InterrogationEngine, ProductContext  # type: ignore

        # Quick smoke test
        engine = InterrogationEngine()
        ctx = ProductContext(
            product_id="test",
            name="Test Product",
            category="electronics",
            price=100,
            cost=50,
        )
        result = engine.interrogate(ctx)

        if getattr(result, "verdict", None) is None:
            return CheckResult("imports_marketing_os", "RED", "InterrogationEngine no produce verdict")

        return CheckResult("imports_marketing_os", "GREEN", "Marketing OS OK (smoke test passed)")

    except ImportError as e:
        return CheckResult("imports_marketing_os", "RED", "Marketing OS no importable", str(e))
    except Exception as e:
        return CheckResult("imports_marketing_os", "RED", "Marketing OS error en smoke test", str(e))


def check_encoding_utf8() -> CheckResult:
    """Verifica encoding UTF-8 en archivos críticos."""
    critical_files = [
        Path("data/launch/dossier_dropi_f1.md"),
        Path("data/launch/shortlist_dropi_f1.csv"),
    ]

    issues = []
    for f in critical_files:
        if not f.exists():
            continue
        try:
            content = f.read_bytes()
            content.decode("utf-8")
        except UnicodeDecodeError:
            issues.append(str(f))

    if issues:
        return CheckResult("encoding_utf8", "YELLOW", f"Posibles issues UTF-8: {len(issues)}", "; ".join(issues))

    return CheckResult("encoding_utf8", "GREEN", "Encoding OK")


def check_ledger_writable() -> CheckResult:
    """Verifica que se puede escribir al ledger."""
    ledger_dir = Path("data/ledger")

    try:
        ledger_dir.mkdir(parents=True, exist_ok=True)

        test_file = ledger_dir / "_doctor_test.tmp"
        test_file.write_text("test", encoding="utf-8")
        test_file.unlink()

        return CheckResult("ledger_writable", "GREEN", "Ledger directory writable")
    except Exception as e:
        return CheckResult("ledger_writable", "RED", "No se puede escribir en ledger", str(e))


def check_disk_space() -> CheckResult:
    """Verifica espacio en disco."""
    try:
        import shutil
        total, used, free = shutil.disk_usage(".")
        free_gb = free / (1024 ** 3)

        if free_gb < 1:
            return CheckResult("disk_space", "RED", f"Poco espacio: {free_gb:.1f} GB")
        elif free_gb < 5:
            return CheckResult("disk_space", "YELLOW", f"Espacio bajo: {free_gb:.1f} GB")

        return CheckResult("disk_space", "GREEN", f"Espacio OK: {free_gb:.1f} GB libres")
    except Exception as e:
        return CheckResult("disk_space", "YELLOW", "No se pudo verificar espacio", str(e))


# ============================================================
# MAIN DOCTOR
# ============================================================

ALL_CHECKS: List[Callable[[], CheckResult]] = [
    check_pack_exists,
    check_canonical_csv,
    check_evidence_fanout,
    check_shortlist,
    check_pytest_config,
    check_imports_core,
    check_imports_marketing_os,
    check_encoding_utf8,
    check_ledger_writable,
    check_disk_space,
]


def run_doctor(verbose: bool = True) -> Tuple[Status, List[CheckResult]]:
    """
    Ejecuta todos los checks.
    Returns:
        (overall_status, list of results)
    """
    results: List[CheckResult] = []

    for check_fn in ALL_CHECKS:
        try:
            result = check_fn()
        except Exception as e:
            result = CheckResult(check_fn.__name__, "RED", "Check crashed", str(e))
        results.append(result)

    statuses = [r.status for r in results]
    if "RED" in statuses:
        overall: Status = "RED"
    elif "YELLOW" in statuses:
        overall = "YELLOW"
    else:
        overall = "GREEN"

    if verbose:
        print_report(overall, results)

    return overall, results


def print_report(overall: Status, results: List[CheckResult]):
    """Imprime reporte formateado."""
    colors = {
        "GREEN": "\033[92m",
        "YELLOW": "\033[93m",
        "RED": "\033[91m",
        "RESET": "\033[0m",
    }

    green = colors["GREEN"]
    yellow = colors["YELLOW"]
    red = colors["RED"]
    reset = colors["RESET"]

    print("\n" + "=" * 60)
    print("SYNAPSE DOCTOR REPORT")
    print("=" * 60)

    for r in results:
        if r.status == "GREEN":
            icon = f"{green}✓{reset}"
        elif r.status == "YELLOW":
            icon = f"{yellow}⚠{reset}"
        else:
            icon = f"{red}✗{reset}"

        print(f"{icon} [{r.status:6}] {r.name}: {r.message}")
        if r.detail:
            print(f"           └─ {r.detail}")

    print("=" * 60)

    if overall == "GREEN":
        print(f"{green}OVERALL: GREEN - Sistema operativo{reset}")
    elif overall == "YELLOW":
        print(f"{yellow}OVERALL: YELLOW - Warnings, puede operar con precaución{reset}")
    else:
        print(f"{red}OVERALL: RED - Errores críticos, NO operar{reset}")

    print("=" * 60 + "\n")


def main():
    """Entry point para CLI."""
    overall, _ = run_doctor(verbose=True)

    # Exit code: GREEN/YELLOW = 0, RED = 1
    if overall in ("GREEN", "YELLOW"):
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
