# synapse/legacy/legacy_cleanup.py
"""
Legacy Cleanup — OLEADA 14
=========================

Meta:
- NO borramos legacy (todavía). Primero: inventario + compat mapping + riesgos.
- Detecta archivos legacy conocidos, verifica import, calcula hash por archivo.
- Genera:
  - data/legacy/legacy_report_latest.json
  - data/legacy/legacy_report_latest.md
  - data/legacy/legacy_state.json  (idempotencia)

CLI:
- python -m synapse.legacy.legacy_cleanup --dry-run
- python -m synapse.legacy.legacy_cleanup
- python -m synapse.legacy.legacy_cleanup --force

Principio:
- ACERO, NO HUMO: reporte accionable, no poesía.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------
# Models
# ---------------------------

@dataclass(frozen=True)
class LegacyTarget:
    module: str
    rel_path: str
    role: str
    replacement_hint: str
    action: str  # KEEP | DEPRECATE | MIGRATE | DELETE_AFTER_MIGRATION


@dataclass
class LegacyModuleReport:
    module: str
    rel_path: str
    exists: bool
    import_ok: bool
    file_hash: str
    size_bytes: int
    role: str
    replacement_hint: str
    action: str
    notes: List[str]


@dataclass
class LegacyCleanupReport:
    schema_version: str
    input_hash: str
    modules: List[Dict[str, Any]]
    duplicates: List[str]
    recommendations: List[str]


# ---------------------------
# Config (targets legacy conocidos)
# ---------------------------

LEGACY_TARGETS: List[LegacyTarget] = [
    LegacyTarget(
        module="synapse.bayesian_scoring",
        rel_path="synapse/bayesian_scoring.py",
        role="Legacy scoring",
        replacement_hint="Preferir synapse/*_v2 o módulo actual de scoring (si ya existe).",
        action="DEPRECATE",
    ),
    LegacyTarget(
        module="synapse.forecasting",
        rel_path="synapse/forecasting.py",
        role="Legacy forecasting",
        replacement_hint="Mover forecasting a paquete dedicado si sigue vivo; si no, deprecate.",
        action="DEPRECATE",
    ),
    LegacyTarget(
        module="synapse.product_evaluator",
        rel_path="synapse/product_evaluator.py",
        role="Legacy product evaluator",
        replacement_hint="Consolidar con discovery/product_ranker y quality_gate_v2 si duplican lógica.",
        action="MIGRATE",
    ),
    LegacyTarget(
        module="synapse.quality_gate",
        rel_path="synapse/quality_gate.py",
        role="Legacy quality gate v1",
        replacement_hint="Usar synapse.quality_gate_v2 como default; mantener v1 solo como compat.",
        action="DELETE_AFTER_MIGRATION",
    ),
    LegacyTarget(
        module="synapse.quality_gate_v2",
        rel_path="synapse/quality_gate_v2.py",
        role="Quality gate v2 (base)",
        replacement_hint="Este es el estándar actual.",
        action="KEEP",
    ),
]


# ---------------------------
# Helpers
# ---------------------------

def _sha256_bytes(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()


def _file_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    return _sha256_bytes(path.read_bytes())


def _json_write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _md_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def _json_load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def _input_hash_for(repo_root: Path) -> str:
    # Hash = config + hashes de archivos target (si existen)
    parts: Dict[str, Any] = {"targets": [asdict(t) for t in LEGACY_TARGETS], "files": []}
    for t in LEGACY_TARGETS:
        p = repo_root / Path(t.rel_path)
        parts["files"].append({
            "rel_path": t.rel_path,
            "exists": p.exists(),
            "size": p.stat().st_size if p.exists() else 0,
            "hash": _file_sha256(p) if p.exists() else "",
        })
    blob = json.dumps(parts, ensure_ascii=False, sort_keys=True).encode("utf-8", errors="replace")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def _try_import(module: str) -> Tuple[bool, str]:
    try:
        importlib.import_module(module)
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _detect_duplicates(repo_root: Path) -> List[str]:
    # Heurística simple: archivos que parecen versiones del mismo concepto
    # Ej: quality_gate.py vs quality_gate_v2.py
    dups: List[str] = []
    p1 = repo_root / "synapse" / "quality_gate.py"
    p2 = repo_root / "synapse" / "quality_gate_v2.py"
    if p1.exists() and p2.exists():
        dups.append("quality_gate (v1) vs quality_gate_v2 (v2) coexisten — mantener compat, default v2.")
    return dups


# ---------------------------
# Ledger (best effort)
# ---------------------------

def _get_ledger(repo_root: Path):
    try:
        from synapse.infra.ledger import Ledger  # type: ignore
        return Ledger(str(repo_root / "data" / "ledger"))
    except Exception:
        return None


def _ledger_write(ledger_obj: Any, event_type: str, payload: Dict[str, Any]) -> None:
    if ledger_obj is None:
        return
    if hasattr(ledger_obj, "write"):
        try:
            ledger_obj.write(event_type=event_type, entity_type="system", entity_id="legacy_cleanup", payload=payload)
        except Exception:
            return


# ---------------------------
# Runner
# ---------------------------

class LegacyCleanupRunner:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def run(self, *, dry_run: bool = False, force: bool = False) -> LegacyCleanupReport:
        out_dir = self.repo_root / "data" / "legacy"
        out_dir.mkdir(parents=True, exist_ok=True)

        report_json = out_dir / "legacy_report_latest.json"
        report_md = out_dir / "legacy_report_latest.md"
        state_path = out_dir / "legacy_state.json"

        inp_hash = _input_hash_for(self.repo_root)

        if state_path.exists() and not force:
            prev = _json_load(state_path)
            if prev.get("input_hash") == inp_hash and report_json.exists():
                cached = _json_load(report_json)
                return LegacyCleanupReport(**cached)  # type: ignore

        module_reports: List[LegacyModuleReport] = []
        for t in LEGACY_TARGETS:
            p = self.repo_root / Path(t.rel_path)
            exists = p.exists()
            file_hash = _file_sha256(p) if exists else ""
            size = p.stat().st_size if exists else 0

            notes: List[str] = []
            import_ok = False
            if exists:
                import_ok, err = _try_import(t.module)
                if not import_ok:
                    notes.append(f"Import falla: {err}")
            else:
                notes.append("No existe en repo (ok si ya fue migrado).")

            module_reports.append(
                LegacyModuleReport(
                    module=t.module,
                    rel_path=t.rel_path,
                    exists=exists,
                    import_ok=import_ok if exists else False,
                    file_hash=file_hash,
                    size_bytes=size,
                    role=t.role,
                    replacement_hint=t.replacement_hint,
                    action=t.action,
                    notes=notes,
                )
            )

        duplicates = _detect_duplicates(self.repo_root)

        recommendations: List[str] = []
        # Reglas accionables (sin borrar nada)
        if any((m.exists and not m.import_ok) for m in module_reports):
            recommendations.append("⚠️ Hay legacy que existe pero NO importa — riesgo de runtime. Arreglar imports o aislar.")
        if any((m.action == "DELETE_AFTER_MIGRATION" and m.exists) for m in module_reports):
            recommendations.append("🧹 V1 puede mantenerse como compat, pero marcar como deprecated y evitar nuevos usos.")
        recommendations.append("✅ Default recomendado: quality_gate_v2 como gate principal. El resto solo compat/migración.")
        recommendations.append("✅ No borrar nada hasta que P0/P1 y smoke E2E estén en verde después de migraciones.")

        report = LegacyCleanupReport(
            schema_version="1.0.0",
            input_hash=inp_hash,
            modules=[asdict(m) for m in module_reports],
            duplicates=duplicates,
            recommendations=recommendations,
        )

        md = self._render_md(report)

        if not dry_run:
            _json_write(report_json, asdict(report))
            _md_write(report_md, md)
            _json_write(state_path, {"input_hash": inp_hash})
        else:
            _md_write(report_md, md)
            _json_write(state_path, {"input_hash": inp_hash, "dry_run": True})

        ledger = _get_ledger(self.repo_root)
        _ledger_write(ledger, "LEGACY_CLEANUP_REPORTED", {
            "input_hash": inp_hash,
            "modules": len(report.modules),
            "dry_run": dry_run,
            "report_json": str(report_json),
            "report_md": str(report_md),
        })

        return report

    def _render_md(self, report: LegacyCleanupReport) -> str:
        lines: List[str] = []
        lines.append("# Legacy Cleanup Report (latest)")
        lines.append("")
        lines.append(f"- schema_version: `{report.schema_version}`")
        lines.append(f"- input_hash: `{report.input_hash}`")
        lines.append("")
        lines.append("## Inventario")
        for m in report.modules:
            status = "OK" if (m.get("exists") and m.get("import_ok")) else ("MISSING" if not m.get("exists") else "BROKEN_IMPORT")
            lines.append(f"- **{m.get('module')}** — `{status}`")
            lines.append(f"  - path: `{m.get('rel_path')}`")
            lines.append(f"  - action: `{m.get('action')}`")
            lines.append(f"  - role: {m.get('role')}")
            lines.append(f"  - replacement_hint: {m.get('replacement_hint')}")
            if m.get("exists"):
                lines.append(f"  - size_bytes: `{m.get('size_bytes')}`")
                lines.append(f"  - file_hash: `{m.get('file_hash')}`")
            if m.get("notes"):
                for n in m["notes"]:
                    lines.append(f"  - note: {n}")
            lines.append("")
        lines.append("## Duplicados detectados")
        if not report.duplicates:
            lines.append("- (none)")
        else:
            for d in report.duplicates:
                lines.append(f"- {d}")
        lines.append("")
        lines.append("## Recomendaciones")
        for r in report.recommendations:
            lines.append(f"- {r}")
        lines.append("")
        lines.append("## Next (seguro)")
        lines.append("- Migrar referencias gradualmente a los módulos “v2 / discovery / marketing_os”.")
        lines.append("- Mantener legacy como compat hasta que el repo esté 100% limpio sin romper P0.")
        return "\n".join(lines).strip() + "\n"


def _cli() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="No escribe JSON (solo MD + state)")
    ap.add_argument("--force", action="store_true", help="Ignora idempotencia")
    args = ap.parse_args()

    repo_root = Path(".").resolve()
    runner = LegacyCleanupRunner(repo_root)
    rep = runner.run(dry_run=args.dry_run, force=args.force)
    print(json.dumps(asdict(rep), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
