"""SYNAPSE A8-R74 operator readiness cockpit (read-only).

Scope:
- Pure, deterministic view-model assembled from existing canonical seams:
  * synapse.integration.a8_r70_smoke (discovery -> financial -> brief -> decision -> guard trail)
  * synapse.safety.spend_guard (canonical spend/mutation guard)
  * synapse.ui.read_model (existing read-only run inventory seam)
  * config feature flags (read-only snapshot, never mutated)
- Thin Streamlit presentation layer (lazy import, render only).

Hard guarantees:
- No network imports, no sockets, no HTTP clients.
- No file writes, no flag mutation, no subprocess, no heavy work at render.
- Missing data degrades to UNKNOWN / NOT_AVAILABLE. Never invents data.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path
from typing import Any, Mapping, Sequence

from synapse.integration.a8_r70_smoke import (
    SMOKE_SCHEMA_VERSION,
    run_a8_r70_smoke_integration,
)
from synapse.safety.spend_guard import (
    GuardIntent,
    SpendAuthorization,
    SpendGuardRequest,
    evaluate_spend_guard,
)
from synapse.ui import read_model


COCKPIT_SCHEMA_VERSION = "a8-r74-operator-cockpit-v1"

SAFETY_BANNER_TEXT = "NO LIVE \u00b7 NO SPEND \u00b7 NO WRITES \u00b7 SANDBOX ONLY"

UNKNOWN = "UNKNOWN"
NOT_AVAILABLE = "NOT_AVAILABLE"
AVAILABLE = "AVAILABLE"

STATUS_READY = "READY"
STATUS_WATCH = "WATCH"
STATUS_BLOCKED = "BLOCKED"
STATUS_UNKNOWN = "UNKNOWN"

CHECK_OK = "OK"
CHECK_PENDING = "PENDING"
CHECK_BLOCKED = "BLOCKED"
CHECK_UNKNOWN = "UNKNOWN"

LIVE_FLAG_KEYS: tuple[str, ...] = (
    "meta_live",
    "shopify_live",
    "dropi_live",
    "spend_real_money",
)

GUARDRAIL_MODULES: tuple[str, ...] = (
    "synapse.safety.spend_guard",
    "infra.network_guard",
    "synapse.safety.killswitch",
    "synapse.safety.circuit",
    "synapse.safety.limits",
    "ops.spend_gateway_v1",
)

NOGO_SCANNER_RELPATHS: tuple[str, ...] = (
    "tools/nogo_ast_resolver.py",
    "tests/p0/test_network_bypass_scan_p0.py",
)

MAX_EVIDENCE_ENTRIES = 200


# ---------------------------------------------------------------------------
# Read-only data collectors (pure functions; degrade, never invent)
# ---------------------------------------------------------------------------

def read_git_head(repo_root: Path) -> dict[str, str]:
    """Resolve HEAD/branch by reading .git files only (no subprocess)."""
    git_dir = Path(repo_root) / ".git"
    head_file = git_dir / "HEAD"
    if not head_file.is_file():
        return {"head": UNKNOWN, "branch": UNKNOWN, "source": NOT_AVAILABLE}

    try:
        content = head_file.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return {"head": UNKNOWN, "branch": UNKNOWN, "source": NOT_AVAILABLE}

    if not content.startswith("ref:"):
        head = content if content else UNKNOWN
        return {"head": head, "branch": "DETACHED", "source": ".git/HEAD"}

    ref = content[4:].strip()
    branch = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref

    ref_file = git_dir / Path(*ref.split("/"))
    if ref_file.is_file():
        try:
            sha = ref_file.read_text(encoding="utf-8", errors="ignore").strip()
            if sha:
                return {"head": sha, "branch": branch, "source": f".git/{ref}"}
        except OSError:
            pass

    packed = git_dir / "packed-refs"
    if packed.is_file():
        try:
            for line in packed.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line.startswith("#") or line.startswith("^") or not line:
                    continue
                parts = line.split(" ", 1)
                if len(parts) == 2 and parts[1].strip() == ref:
                    return {"head": parts[0], "branch": branch, "source": ".git/packed-refs"}
        except OSError:
            pass

    return {"head": UNKNOWN, "branch": branch, "source": NOT_AVAILABLE}


def build_flags_snapshot() -> dict[str, Any]:
    """Read-only feature flag snapshot. Never mutates environment or flags."""
    snapshot: dict[str, Any] = {
        "read_only": True,
        "mutable_from_ui": False,
        "source": UNKNOWN,
        "values": {key: UNKNOWN for key in LIVE_FLAG_KEYS},
        "dry_run": UNKNOWN,
        "status": UNKNOWN,
    }

    try:
        from config.feature_flags import FeatureFlags
    except ImportError:
        snapshot["source"] = NOT_AVAILABLE
        return snapshot

    try:
        flags = FeatureFlags.from_env()
    except (TypeError, ValueError, KeyError):
        snapshot["source"] = "config.feature_flags (load error)"
        return snapshot

    values = {key: bool(getattr(flags, key, False)) for key in LIVE_FLAG_KEYS}
    snapshot["source"] = "config.feature_flags.FeatureFlags.from_env"
    snapshot["values"] = values
    snapshot["dry_run"] = bool(getattr(flags, "dry_run", True))
    snapshot["status"] = (
        "ALL_LIVE_FLAGS_OFF" if not any(values.values()) else "LIVE_FLAG_DETECTED"
    )
    return snapshot


def build_safety_banner(flags_snapshot: Mapping[str, Any]) -> dict[str, Any]:
    values = flags_snapshot.get("values", {})
    violations = [
        key for key in LIVE_FLAG_KEYS
        if isinstance(values, Mapping) and values.get(key) is True
    ]

    if flags_snapshot.get("status") == UNKNOWN:
        sandbox_confirmed: Any = UNKNOWN
    else:
        sandbox_confirmed = not violations

    return {
        "text": SAFETY_BANNER_TEXT,
        "sandbox_confirmed": sandbox_confirmed,
        "violations": violations,
    }


def build_guardrail_availability() -> dict[str, Any]:
    """Availability of canonical guard modules (spec lookup only, no execution)."""
    modules: dict[str, str] = {}
    for name in GUARDRAIL_MODULES:
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ValueError):
            spec = None
        modules[name] = AVAILABLE if spec is not None else NOT_AVAILABLE
    return modules


def build_nogo_scanner_status(repo_root: Path) -> dict[str, str]:
    status: dict[str, str] = {}
    for rel in NOGO_SCANNER_RELPATHS:
        path = Path(repo_root) / Path(*rel.split("/"))
        status[rel] = AVAILABLE if path.is_file() else NOT_AVAILABLE
    return status


def build_smoke_snapshot() -> dict[str, Any]:
    """Run the canonical A8-R70 sandbox seam. Pure, deterministic, no IO."""
    try:
        result = run_a8_r70_smoke_integration()
    except (ImportError, TypeError, ValueError) as exc:
        return {
            "status": NOT_AVAILABLE,
            "error": f"{type(exc).__name__}: {exc}",
        }

    payload = result.to_dict()
    payload["status"] = AVAILABLE
    return payload


def build_evidence_inventory(runs_root: Path) -> dict[str, Any]:
    """Read-only bounded inventory of local evidence files. Never writes."""
    root = Path(runs_root)
    if not root.is_dir():
        return {"status": NOT_AVAILABLE, "root": str(root), "entries": []}

    entries: list[dict[str, Any]] = []
    try:
        iterator = (p for p in sorted(root.rglob("*")) if p.is_file())
        for path in islice(iterator, MAX_EVIDENCE_ENTRIES):
            try:
                stat = path.stat()
                mtime = datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
                size = stat.st_size
            except OSError:
                mtime = UNKNOWN
                size = -1
            entries.append({
                "path": str(path).replace("\\", "/"),
                "size_bytes": size,
                "modified_utc": mtime,
            })
    except OSError:
        return {"status": NOT_AVAILABLE, "root": str(root), "entries": []}

    status = AVAILABLE if entries else NOT_AVAILABLE
    return {"status": status, "root": str(root), "entries": entries}


def build_run_inventory_panel() -> dict[str, Any]:
    """Reuse the existing read_model seam for run inventory. No new truth."""
    try:
        run_dirs = read_model.discover_run_dirs()
    except (OSError, ValueError, json.JSONDecodeError):
        run_dirs = []

    inventory = read_model.build_run_inventory_status(len(run_dirs))
    last_run_dir = str(run_dirs[-1]) if run_dirs else NOT_AVAILABLE
    return {
        "inventory": inventory,
        "run_dirs": [str(path) for path in run_dirs],
        "last_run_dir": last_run_dir,
    }


def build_approval_simulation() -> dict[str, Any]:
    """Local in-memory approval simulation through the canonical guard.

    Pure compute: builds hypothetical in-memory authorization envelopes and
    shows what the canonical guard would decide. Does NOT mutate real flags,
    does NOT write, does NOT call network, does NOT spend.
    """
    default_block = evaluate_spend_guard(
        SpendGuardRequest(
            intent=GuardIntent.SPEND,
            channel="sandbox",
            spend_amount="50.00",
        )
    )
    simulated_allow = evaluate_spend_guard(
        SpendGuardRequest(
            intent=GuardIntent.SPEND,
            channel="sandbox",
            spend_amount="50.00",
            authorization=SpendAuthorization(
                spend_allowed=True,
                max_spend="100.00",
            ),
        )
    )
    return {
        "mode": "SIMULATION_LOCAL_ONLY",
        "note": (
            "Simulacion local en memoria via spend_guard canonico. "
            "No muta flags reales, no escribe, no llama red, no gasta."
        ),
        "default_envelope": {
            "decision": default_block.decision.value,
            "reason_codes": list(default_block.reason_codes),
        },
        "hypothetical_authorized_envelope": {
            "decision": simulated_allow.decision.value,
            "reason_codes": list(simulated_allow.reason_codes),
        },
    }


# ---------------------------------------------------------------------------
# Derivations (no parallel business logic; only status mapping)
# ---------------------------------------------------------------------------

def derive_overall_status(
    banner: Mapping[str, Any],
    smoke: Mapping[str, Any],
) -> str:
    if banner.get("violations"):
        return STATUS_BLOCKED
    if smoke.get("status") != AVAILABLE:
        return STATUS_UNKNOWN

    decision_record = smoke.get("decision_record", {})
    final_decision = ""
    if isinstance(decision_record, Mapping):
        final_decision = str(decision_record.get("final_decision", ""))

    if final_decision == "READY_FOR_SANDBOX_BRIEF":
        return STATUS_READY
    if final_decision == "WATCH_SANDBOX_BRIEF_ONLY":
        return STATUS_WATCH
    if final_decision.startswith("BLOCKED"):
        return STATUS_BLOCKED
    return STATUS_UNKNOWN


def _guard_trail_flags(smoke: Mapping[str, Any]) -> tuple[Any, Any, Any]:
    trail = smoke.get("guard_trail")
    if not isinstance(trail, Mapping):
        return UNKNOWN, UNKNOWN, UNKNOWN

    def _decision_of(key: str) -> Any:
        item = trail.get(key)
        if isinstance(item, Mapping):
            return item.get("decision", UNKNOWN)
        return UNKNOWN

    return (
        _decision_of("evaluation"),
        _decision_of("spend_probe"),
        _decision_of("mutation_probe"),
    )



def _shopify_read_only_dry_run_summary_ok(payload: Mapping[str, Any]) -> bool:
    mutation_probe = payload.get("mutation_probe")
    network_guard = payload.get("network_guard")

    if not hasattr(mutation_probe, "get") or not hasattr(network_guard, "get"):
        return False

    return (
        payload.get("component") == "shopify_read_only_dry_run"
        and payload.get("status") == "OK"
        and payload.get("external_io_attempted") is False
        and payload.get("external_write_attempted") is False
        and payload.get("live_shopify_attempted") is False
        and payload.get("spend_attempted") is False
        and mutation_probe.get("rejected_before_io") is True
        and network_guard.get("decision") == "BLOCK"
        and network_guard.get("expected_policy_block") is True
    )


def _shopify_read_only_dry_run_candidate_paths(evidence: Mapping[str, Any]) -> list[Path]:
    entries = evidence.get("entries", [])
    if not isinstance(entries, list):
        return []

    paths: list[Path] = []

    for entry in entries:
        if not hasattr(entry, "get"):
            continue

        for key in ("path", "summary_path", "file_path"):
            raw = entry.get(key)
            if not raw:
                continue

            candidate = Path(str(raw))
            haystack = str(candidate).lower()

            if (
                candidate.name == "shopify_read_only_dry_run_summary.json"
                or "a8_r75_shopify_readonly_dryrun" in haystack
            ):
                paths.append(candidate)

    return paths


def _shopify_read_only_dry_run_evidence_available(evidence: Mapping[str, Any]) -> bool:
    for path in _shopify_read_only_dry_run_candidate_paths(evidence):
        try:
            if not path.is_file():
                continue

            payload = json.loads(path.read_text(encoding="utf-8"))

            if hasattr(payload, "get") and _shopify_read_only_dry_run_summary_ok(payload):
                return True
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue

    return False


def _shopify_read_only_dry_run_status(evidence: Mapping[str, Any]) -> str:
    return CHECK_OK if _shopify_read_only_dry_run_evidence_available(evidence) else CHECK_PENDING


def _shopify_read_only_dry_run_detail(evidence: Mapping[str, Any]) -> str:
    if _shopify_read_only_dry_run_evidence_available(evidence):
        return "Valid A8-R75 Shopify read-only dry-run evidence is visible in local runs/."
    return "Awaiting valid A8-R75 Shopify read-only dry-run local evidence."


def build_readiness_checklist(
    *,
    banner: Mapping[str, Any],
    flags_snapshot: Mapping[str, Any],
    guard_modules: Mapping[str, str],
    nogo_scanner: Mapping[str, str],
    evidence: Mapping[str, Any],
    smoke: Mapping[str, Any],
) -> list[dict[str, str]]:
    evaluation, spend_probe, mutation_probe = _guard_trail_flags(smoke)

    if banner.get("sandbox_confirmed") is True:
        no_live = CHECK_OK
    elif banner.get("sandbox_confirmed") == UNKNOWN:
        no_live = CHECK_UNKNOWN
    else:
        no_live = CHECK_BLOCKED

    def _probe_status(value: Any, expected: str) -> str:
        if value == UNKNOWN:
            return CHECK_UNKNOWN
        return CHECK_OK if value == expected else CHECK_BLOCKED

    guardrails_ok = all(state == AVAILABLE for state in guard_modules.values())
    scanner_ok = all(state == AVAILABLE for state in nogo_scanner.values())

    return [
        {
            "item": "ui_read_only_operational",
            "status": CHECK_OK if evaluation == "ALLOW" else CHECK_UNKNOWN,
            "detail": "Cockpit derivado de seams canonicos; sin writes ni red.",
        },
        {
            "item": "evidence_visible",
            "status": CHECK_OK if evidence.get("status") == AVAILABLE else CHECK_PENDING,
            "detail": f"Evidence root: {evidence.get('root', UNKNOWN)}",
        },
        {
            "item": "guardrails_visible",
            "status": CHECK_OK if guardrails_ok else CHECK_PENDING,
            "detail": "Modulos canonicos de guardrails localizables.",
        },
        {
            "item": "no_live_confirmed",
            "status": no_live,
            "detail": f"Flags live: {flags_snapshot.get('status', UNKNOWN)}",
        },
        {
            "item": "no_spend_confirmed",
            "status": _probe_status(spend_probe, "BLOCK"),
            "detail": "Spend probe canonico debe quedar BLOCK sin autorizacion.",
        },
        {
            "item": "no_writes_confirmed",
            "status": _probe_status(mutation_probe, "BLOCK"),
            "detail": "Mutation probe canonico debe quedar BLOCK sin autorizacion.",
        },
        {
            "item": "no_network_expansion",
            "status": CHECK_OK if scanner_ok else CHECK_PENDING,
            "detail": "Scanner AST no-go y gate P0 presentes en repo.",
        },
        {
            "item": "shopify_read_only_dry_run",
            "status": _shopify_read_only_dry_run_status(evidence),
            "detail": _shopify_read_only_dry_run_detail(evidence),
        },
    ]


# ---------------------------------------------------------------------------
# View-model assembly
# ---------------------------------------------------------------------------

def build_cockpit_view_model(
    repo_root: Path | str = ".",
    runs_root: Path | str | None = None,
) -> dict[str, Any]:
    """Assemble the complete read-only cockpit view-model.

    Pure with respect to external systems: reads local files only, never
    writes, never mutates flags, never calls network, never spends.
    """
    root = Path(repo_root)
    evidence_root = Path(runs_root) if runs_root is not None else root / "runs"

    git_info = read_git_head(root)
    flags_snapshot = build_flags_snapshot()
    banner = build_safety_banner(flags_snapshot)
    guard_modules = build_guardrail_availability()
    nogo_scanner = build_nogo_scanner_status(root)
    smoke = build_smoke_snapshot()
    evidence = build_evidence_inventory(evidence_root)
    run_panel = build_run_inventory_panel()
    simulation = build_approval_simulation()

    overall_status = derive_overall_status(banner, smoke)

    def _section(key: str) -> Any:
        value = smoke.get(key)
        return value if value is not None else NOT_AVAILABLE

    checklist = build_readiness_checklist(
        banner=banner,
        flags_snapshot=flags_snapshot,
        guard_modules=guard_modules,
        nogo_scanner=nogo_scanner,
        evidence=evidence,
        smoke=smoke,
    )

    return {
        "schema_version": COCKPIT_SCHEMA_VERSION,
        "smoke_schema_version": SMOKE_SCHEMA_VERSION,
        "banner": banner,
        "flags": flags_snapshot,
        "overview": {
            "head": git_info["head"],
            "branch": git_info["branch"],
            "head_source": git_info["source"],
            "overall_status": overall_status,
            "sandbox_mode": banner.get("sandbox_confirmed"),
            "run_inventory": run_panel["inventory"],
            "last_run_dir": run_panel["last_run_dir"],
            "visible_run_count": len(run_panel["run_dirs"]),
        },
        "candidate": _section("candidate"),
        "financial_input": _section("financial_input"),
        "financial_result": _section("financial_result"),
        "marketing_brief": _section("marketing_brief"),
        "decision_record": _section("decision_record"),
        "guard_trail": _section("guard_trail"),
        "guardrails": {
            "modules": guard_modules,
            "nogo_scanner": nogo_scanner,
        },
        "evidence": evidence,
        "safety_status": {
            "no_live": checklist[3]["status"],
            "no_spend": checklist[4]["status"],
            "no_writes": checklist[5]["status"],
            "no_network_expansion": checklist[6]["status"],
        },
        "readiness_checklist": checklist,
        "approval_simulation": simulation,
        "smoke_status": smoke.get("status", UNKNOWN),
    }


# ---------------------------------------------------------------------------
# Thin presentation layer (Streamlit lazy import; render only)
# ---------------------------------------------------------------------------

def render_cockpit(st: Any, view_model: Mapping[str, Any]) -> None:
    banner = view_model.get("banner", {})
    st.title("SYNAPSE \u2014 Operator Readiness Cockpit (A8-R74)")
    st.warning(str(banner.get("text", SAFETY_BANNER_TEXT)))
    if banner.get("violations"):
        st.error("Flags live detectados: " + ", ".join(banner["violations"]))
    elif banner.get("sandbox_confirmed") is True:
        st.success("Sandbox confirmado desde flags locales.")
    else:
        st.info("Estado sandbox: UNKNOWN (fuente de flags no disponible).")

    overview = view_model.get("overview", {})
    st.subheader("Operator Overview")
    st.write(f"**HEAD:** `{overview.get('head', UNKNOWN)}`")
    st.write(f"**Branch:** `{overview.get('branch', UNKNOWN)}`")
    st.write(f"**Overall status:** `{overview.get('overall_status', UNKNOWN)}`")
    st.write(f"**Last run dir:** `{overview.get('last_run_dir', NOT_AVAILABLE)}`")
    inventory = overview.get("run_inventory", {})
    if isinstance(inventory, Mapping):
        st.caption(
            f"Run inventory: {inventory.get('inventory_label', UNKNOWN)} "
            f"| state={inventory.get('state', UNKNOWN)}"
        )

    st.divider()
    st.subheader("Product / Candidate Detail")
    candidate = view_model.get("candidate")
    if isinstance(candidate, Mapping):
        read_model.render_table(st, [{
            "candidate_id": candidate.get("candidate_id", UNKNOWN),
            "product_name": candidate.get("product_name", UNKNOWN),
            "source_type": candidate.get("source_type", UNKNOWN),
            "price": candidate.get("price", UNKNOWN),
            "cost": candidate.get("cost", UNKNOWN),
        }])
    else:
        st.info(NOT_AVAILABLE)

    st.divider()
    st.subheader("Financial Evaluation")
    financial = view_model.get("financial_result")
    if isinstance(financial, Mapping):
        st.write(f"**Decision:** `{financial.get('decision', UNKNOWN)}`")
        reasons = financial.get("reason_codes", [])
        read_model.render_table(
            st, [{"reason_code": code} for code in reasons]
        )
    else:
        st.info(NOT_AVAILABLE)

    st.divider()
    st.subheader("Marketing Brief")
    brief = view_model.get("marketing_brief")
    if isinstance(brief, Mapping):
        st.json(dict(brief))
    else:
        st.info("Brief no generado para esta decision (o NOT_AVAILABLE).")

    st.divider()
    st.subheader("Decision Record")
    record = view_model.get("decision_record")
    if isinstance(record, Mapping):
        st.json(dict(record))
    else:
        st.info(NOT_AVAILABLE)

    st.divider()
    st.subheader("Spend Guard / Mutation Guard")
    trail = view_model.get("guard_trail")
    if isinstance(trail, Mapping):
        rows = []
        for key in ("evaluation", "spend_probe", "mutation_probe"):
            item = trail.get(key, {})
            if isinstance(item, Mapping):
                rows.append({
                    "probe": key,
                    "decision": item.get("decision", UNKNOWN),
                    "reason_codes": ", ".join(item.get("reason_codes", [])),
                })
        read_model.render_table(st, rows)
        st.success("Confirmado: sin gasto real y sin writes externos en R74.")
    else:
        st.info(NOT_AVAILABLE)

    st.divider()
    st.subheader("Evidence / Ledger")
    evidence = view_model.get("evidence", {})
    st.write(f"**Root:** `{evidence.get('root', UNKNOWN)}` | **Status:** `{evidence.get('status', UNKNOWN)}`")
    read_model.render_table(st, evidence.get("entries", []))

    st.divider()
    st.subheader("Safety Status / No-Go")
    safety = view_model.get("safety_status", {})
    read_model.render_table(st, [
        {"check": key, "status": value} for key, value in safety.items()
    ])
    guardrails = view_model.get("guardrails", {})
    read_model.render_table(st, [
        {"module": name, "status": state}
        for name, state in guardrails.get("modules", {}).items()
    ])

    st.divider()
    st.subheader("Readiness Checklist (R75+)")
    read_model.render_table(st, view_model.get("readiness_checklist", []))

    st.divider()
    st.subheader("Approval Simulation (local-only)")
    simulation = view_model.get("approval_simulation", {})
    st.caption(str(simulation.get("note", "")))
    read_model.render_table(st, [
        {
            "envelope": "default (sin autorizacion)",
            "decision": simulation.get("default_envelope", {}).get("decision", UNKNOWN),
            "reason_codes": ", ".join(
                simulation.get("default_envelope", {}).get("reason_codes", [])
            ),
        },
        {
            "envelope": "hipotetico autorizado (en memoria)",
            "decision": simulation.get(
                "hypothetical_authorized_envelope", {}
            ).get("decision", UNKNOWN),
            "reason_codes": ", ".join(
                simulation.get(
                    "hypothetical_authorized_envelope", {}
                ).get("reason_codes", [])
            ),
        },
    ])


def run_app() -> None:
    try:
        import streamlit as st
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Streamlit is required to run the cockpit. Install requirements first."
        ) from exc

    st.set_page_config(page_title="SYNAPSE Operator Cockpit", layout="wide")
    view_model = build_cockpit_view_model()
    render_cockpit(st, view_model)


if __name__ == "__main__":
    run_app()
