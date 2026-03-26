from __future__ import annotations

import dataclasses
import importlib
import inspect
import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any


EXPECTED_VAULT_FIELDS = {
    "total_budget",
    "learning_budget",
    "operational_budget",
    "reserve_budget",
    "spent_learning",
    "spent_operational",
}

EXPECTED_PRODUCT_FIELDS = {
    "product_id",
    "title",
    "category",
    "price",
    "cost",
    "rating",
    "reviews",
    "sales",
    "supplier_id",
    "supplier_name",
    "shipping_days",
    "image_url",
    "images_count",
    "margin_percent",
    "margin_absolute",
    "keyword_matches",
    "match_score",
}

EXPECTED_FLAGS_FIELDS = {
    "meta_live",
    "shopify_live",
    "dropi_live",
    "spend_real_money",
}

NOMINAL_OPS_TICK = {
    "timestamp": "2026-03-24T11:00:00-06:00",
    "ts": "2026-03-24T11:00:00-06:00",
    "status": "healthy",
    "healthy": True,
    "meta": {"api_ok": True, "ad_account_ok": True, "latency_ms": 220},
    "shopify": {"api_ok": True, "checkout_ok": True, "orders_last_hour": 0},
    "dropi": {"api_ok": True, "inventory_ok": True, "price_drift_detected": False},
    "finance": {
        "cash_ok": True,
        "reserve_ok": True,
        "negative_margin_detected": False,
        "refund_pressure": 0.0,
        "chargeback_pressure": 0.0,
    },
    "circuit_breaker": {"open": False, "reason": None, "trip_count": 0},
    "flags": {
        "meta_live": False,
        "shopify_live": False,
        "dropi_live": False,
        "spend_real_money": False,
    },
}

BREAKER_OPEN_OPS_TICK = {
    "timestamp": "2026-03-24T11:05:00-06:00",
    "ts": "2026-03-24T11:05:00-06:00",
    "status": "degraded",
    "healthy": False,
    "meta": {"api_ok": False, "ad_account_ok": False, "latency_ms": 1800},
    "shopify": {"api_ok": True, "checkout_ok": True, "orders_last_hour": 0},
    "dropi": {"api_ok": False, "inventory_ok": False, "price_drift_detected": True},
    "finance": {
        "cash_ok": False,
        "reserve_ok": False,
        "negative_margin_detected": True,
        "refund_pressure": 0.22,
        "chargeback_pressure": 0.08,
    },
    "circuit_breaker": {"open": True, "reason": "reserve_floor_breached", "trip_count": 2},
    "flags": {
        "meta_live": False,
        "shopify_live": False,
        "dropi_live": False,
        "spend_real_money": False,
    },
}

PRODUCTS = [
    {
        "product_id": "prod-alpha",
        "title": "Neck Fan Pro",
        "category": "gadgets",
        "price": 499.0,
        "cost": 219.0,
        "rating": 4.4,
        "reviews": 1842,
        "sales": 920,
        "supplier_id": "sup-001",
        "supplier_name": "Dropi Alpha",
        "shipping_days": 5,
        "image_url": "https://example.com/alpha.jpg",
        "images_count": 4,
        "margin_percent": 56.11,
        "margin_absolute": 280.0,
        "keyword_matches": ["summer", "portable", "handsfree"],
        "match_score": 0.88,
    },
    {
        "product_id": "prod-beta",
        "title": "Desk Cooler Mini",
        "category": "gadgets",
        "price": 699.0,
        "cost": 331.0,
        "rating": 4.2,
        "reviews": 967,
        "sales": 410,
        "supplier_id": "sup-002",
        "supplier_name": "Dropi Beta",
        "shipping_days": 7,
        "image_url": "https://example.com/beta.jpg",
        "images_count": 5,
        "margin_percent": 52.65,
        "margin_absolute": 368.0,
        "keyword_matches": ["office", "portable", "summer"],
        "match_score": 0.81,
    },
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _import(name: str):
    return importlib.import_module(name)


def _safe_signature(obj: Any) -> str:
    try:
        return str(inspect.signature(obj))
    except Exception as exc:
        return f"<signature-unavailable:{type(exc).__name__}:{exc}>"


def _expected_fields(obj: Any) -> set[str]:
    try:
        if dataclasses.is_dataclass(obj):
            return {f.name for f in dataclasses.fields(obj)}
    except Exception:
        pass

    try:
        sig = inspect.signature(obj)
        names = set()
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            if param.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY):
                names.add(name)
        return names
    except Exception:
        return set()


def _serialize(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj):
        return {f.name: _serialize(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_serialize(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if hasattr(obj, "__dict__"):
        return _serialize(vars(obj))
    return repr(obj)


def _call_with_supported(target: Any, pool: dict[str, Any]) -> Any:
    sig = inspect.signature(target)
    accepts_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    if accepts_var_kw:
        return target(**pool)

    kwargs = {}
    for name in sig.parameters:
        if name in pool:
            kwargs[name] = pool[name]
    return target(**kwargs)


def _resolve_callable(module_or_obj: Any, names: list[str]) -> tuple[Any | None, str | None]:
    for name in names:
        value = getattr(module_or_obj, name, None)
        if callable(value):
            return value, name
    return None, None


def _normalized_ops_tick(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(payload))
    checks = dict(normalized.get("checks") or {})
    cb_open = bool(((normalized.get("circuit_breaker") or {}).get("open")))
    checks.setdefault(
        "reconcile_preflight",
        {"status": "blocked" if cb_open else "ok", "blocked": cb_open},
    )
    normalized["checks"] = checks
    normalized.setdefault("ts_utc", normalized.get("timestamp") or normalized.get("ts"))
    return normalized


def _workspace(repo_root: Path, scenario_name: str, ops_tick_payload: dict[str, Any]) -> Path:
    ws = Path(tempfile.mkdtemp(prefix=f"synapse_capa_b_{scenario_name}_"))
    config_src = repo_root / "config"
    if config_src.exists():
        shutil.copytree(config_src, ws / "config", dirs_exist_ok=True)

    (ws / "data" / "run").mkdir(parents=True, exist_ok=True)
    (ws / "artifacts" / "decision_journal").mkdir(parents=True, exist_ok=True)
    (ws / "artifacts" / "creative_tracker").mkdir(parents=True, exist_ok=True)
    (ws / "artifacts" / "decisions").mkdir(parents=True, exist_ok=True)

    normalized = _normalized_ops_tick(ops_tick_payload)
    with (ws / "data" / "run" / "ops_tick.json").open("w", encoding="utf-8") as fh:
        json.dump(normalized, fh, indent=2, ensure_ascii=False)

    return ws


def _build_instance(target: Any, payload: dict[str, Any]) -> Any:
    try:
        return _call_with_supported(target, payload)
    except TypeError:
        instance = target()
        for key, value in payload.items():
            try:
                setattr(instance, key, value)
            except Exception:
                pass
        return instance


def _load_products(ProductCandidate: Any) -> list[Any]:
    return [_build_instance(ProductCandidate, item) for item in PRODUCTS]


def _actions_blob(result: Any) -> str:
    return json.dumps(_serialize(result), sort_keys=True).lower()


def _looks_blocked(serialized: Any) -> bool:
    text = _actions_blob(serialized)
    blocked_tokens = [
        "emergency_stop",
        "pause_all",
        "circuit_breaker_open",
        "kill_switch_active",
        "reconcile_integrity",
        "blocked",
        "halted",
        "denied",
        "skipped",
        "trip",
        "breaker",
    ]
    return any(token in text for token in blocked_tokens)


def _public_callable_names(module: Any) -> list[str]:
    names = []
    for name in dir(module):
        if name.startswith("_"):
            continue
        try:
            value = getattr(module, name)
        except Exception:
            continue
        if callable(value):
            names.append(name)
    return sorted(names)


def _probe_decision_journal(repo_root: Path) -> dict[str, Any]:
    module = _import("synapse.core.decision_journal")

    ctor, ctor_name = _resolve_callable(
        module,
        ["DecisionJournal", "Journal", "DecisionJournalStore", "StructuredDecisionJournal"],
    )

    public_callables = _public_callable_names(module)
    if ctor is None and not public_callables:
        raise LookupError("decision_journal surface not found")

    selected_method = None
    selected_sig = None

    if ctor is not None:
        for meth_name in ["append", "record", "add_entry", "log_decision", "write", "track"]:
            meth = getattr(ctor, meth_name, None)
            if callable(meth):
                selected_method = meth_name
                selected_sig = _safe_signature(meth)
                break

    if selected_method is None:
        fn, fn_name = _resolve_callable(
            module,
            ["append_decision", "record_decision", "log_decision", "write_decision"],
        )
        if fn is not None:
            selected_method = fn_name
            selected_sig = _safe_signature(fn)

    return {
        "status": "ok",
        "ctor_name": ctor_name,
        "ctor_signature": _safe_signature(ctor) if ctor is not None else None,
        "selected_method": selected_method,
        "selected_signature": selected_sig,
        "public_callables": public_callables[:12],
        "probe_mode": "contract_surface",
    }


def _probe_creative_tracker(repo_root: Path) -> dict[str, Any]:
    module = _import("synapse.core.creative_tracker")

    ctor, ctor_name = _resolve_callable(
        module,
        ["CreativeTracker", "Tracker", "CreativeRotationTracker"],
    )

    public_callables = _public_callable_names(module)

    preferred_surface = []
    for name in public_callables:
        lowered = name.lower()
        if any(token in lowered for token in ["creative", "variant", "rotate", "track"]):
            preferred_surface.append(name)

    if ctor is None and not preferred_surface and not public_callables:
        raise LookupError("creative_tracker surface not found")

    selected = None
    selected_sig = None

    if ctor is not None:
        for meth_name in [
            "rotate_creative",
            "select_next",
            "evaluate_rotation",
            "record",
            "track",
            "best_variant",
            "winner",
        ]:
            meth = getattr(ctor, meth_name, None)
            if callable(meth):
                selected = f"{ctor_name}.{meth_name}"
                selected_sig = _safe_signature(meth)
                break

    if selected is None:
        fn, fn_name = _resolve_callable(
            module,
            [
                "rotate_creative",
                "select_next_creative",
                "evaluate_rotation",
                "best_variant",
                "winner",
                "track_creatives",
            ],
        )
        if fn is not None:
            selected = fn_name
            selected_sig = _safe_signature(fn)

    if selected is None and preferred_surface:
        selected = preferred_surface[0]
        selected_sig = _safe_signature(getattr(module, selected))

    return {
        "status": "ok",
        "ctor_name": ctor_name,
        "ctor_signature": _safe_signature(ctor) if ctor is not None else None,
        "selected_surface": selected,
        "selected_signature": selected_sig,
        "public_callables": public_callables[:12],
        "probe_mode": "contract_surface",
    }


def _run_scenario(
    repo_root: Path,
    name: str,
    ops_tick_payload: dict[str, Any],
    vault_payload: dict[str, Any],
    flags_payload: dict[str, Any],
) -> dict[str, Any]:
    ws = _workspace(repo_root, name, ops_tick_payload)

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    vault_module = _import("infra.vault")
    catalog_module = _import("synapse.discovery.catalog_scanner")
    feature_flags_module = _import("config.feature_flags")
    orchestrator_module = _import("synapse.core.orchestrator")

    VaultSnapshot = getattr(vault_module, "VaultSnapshot")
    ProductCandidate = getattr(catalog_module, "ProductCandidate")
    FeatureFlags = getattr(feature_flags_module, "FeatureFlags")
    decide = getattr(orchestrator_module, "decide", None)

    if not callable(decide):
        raise LookupError("decide entrypoint not found")

    products = _load_products(ProductCandidate)
    vault = _build_instance(VaultSnapshot, vault_payload)
    flags = _build_instance(FeatureFlags, flags_payload)

    breaker_open = bool(((ops_tick_payload.get("circuit_breaker") or {}).get("open")))
    breaker_status = "open" if breaker_open else "closed"

    creative_registry = [
        SimpleNamespace(product_id="prod-alpha", variant_id="v1", roas=2.5),
        SimpleNamespace(product_id="prod-alpha", variant_id="v2", roas=1.1),
    ]
    campaign_snapshots = []

    exception_text = None
    result = None

    try:
        result = decide(
            vault=vault,
            discovery_shortlist=products,
            creative_registry=creative_registry,
            campaign_snapshots=campaign_snapshots,
            breaker_status=breaker_status,
            kill_switch_active=False,
            feature_flags=flags,
            ops_tick_path=str(ws / "data" / "run" / "ops_tick.json"),
            ledger_rows=[],
            decisions_dir=str(ws / "artifacts" / "decisions"),
            thresholds_path=str(repo_root / "config" / "thresholds.yaml"),
        )
    except Exception as exc:
        exception_text = f"{type(exc).__name__}: {exc}"

    actions_text = _actions_blob(result) if result is not None else ""

    if name == "nominal":
        scenario_status = "ok" if (
            exception_text is None
            and "launch_test" in actions_text
            and "rotate_creative" in actions_text
        ) else "error"
    else:
        scenario_status = "ok" if (
            exception_text is None
            and ("emergency_stop" in actions_text or _looks_blocked(result))
        ) else "error"

    return {
        "status": scenario_status,
        "workspace": str(ws),
        "exception": exception_text,
        "result": _serialize(result),
    }


def run_all() -> dict[str, Any]:
    repo_root = _repo_root()
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    import_targets = {
        "vault": "infra.vault",
        "catalog_scanner": "synapse.discovery.catalog_scanner",
        "feature_flags": "config.feature_flags",
        "core_models": "synapse.core.models",
        "decision_journal": "synapse.core.decision_journal",
        "creative_tracker": "synapse.core.creative_tracker",
        "orchestrator": "synapse.core.orchestrator",
        "ledger_v2": "infra.ledger_v2",
        "circuit_breaker": "synapse.infra.circuit_breaker",
    }

    imports: dict[str, Any] = {}
    loaded: dict[str, Any] = {}
    contract_errors: list[str] = []

    for label, module_name in import_targets.items():
        try:
            mod = _import(module_name)
            loaded[label] = mod
            imports[label] = {"status": "ok", "module": module_name}
        except Exception as exc:
            imports[label] = {
                "status": "error",
                "module": module_name,
                "error": f"{type(exc).__name__}: {exc}",
            }
            contract_errors.append(f"import:{module_name}:{type(exc).__name__}:{exc}")

    if not contract_errors:
        vault_cls = getattr(loaded["vault"], "VaultSnapshot", None)
        product_cls = getattr(loaded["catalog_scanner"], "ProductCandidate", None)
        flags_cls = getattr(loaded["feature_flags"], "FeatureFlags", None)

        if vault_cls is None:
            contract_errors.append("missing:VaultSnapshot")
        else:
            vault_fields = _expected_fields(vault_cls)
            missing = sorted(EXPECTED_VAULT_FIELDS - vault_fields)
            if missing:
                contract_errors.append(f"VaultSnapshot fields missing: {','.join(missing)}")
            imports["vault"]["VaultSnapshot_fields"] = sorted(vault_fields)

        if product_cls is None:
            contract_errors.append("missing:ProductCandidate")
        else:
            product_fields = _expected_fields(product_cls)
            missing = sorted(EXPECTED_PRODUCT_FIELDS - product_fields)
            if missing:
                contract_errors.append(f"ProductCandidate fields missing: {','.join(missing)}")
            imports["catalog_scanner"]["ProductCandidate_fields"] = sorted(product_fields)

        if flags_cls is None:
            contract_errors.append("missing:FeatureFlags")
        else:
            flags_fields = _expected_fields(flags_cls)
            missing = sorted(EXPECTED_FLAGS_FIELDS - flags_fields)
            if missing:
                contract_errors.append(f"FeatureFlags fields missing: {','.join(missing)}")
            imports["feature_flags"]["FeatureFlags_fields"] = sorted(flags_fields)

    probes: dict[str, Any] = {}
    scenarios: dict[str, Any] = {}

    if not contract_errors:
        try:
            probes["decision_journal"] = _probe_decision_journal(repo_root)
        except Exception as exc:
            probes["decision_journal"] = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}

        try:
            probes["creative_tracker"] = _probe_creative_tracker(repo_root)
        except Exception as exc:
            probes["creative_tracker"] = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}

        scenarios["nominal"] = _run_scenario(
            repo_root=repo_root,
            name="nominal",
            ops_tick_payload=NOMINAL_OPS_TICK,
            vault_payload={
                "total_budget": 2000.0,
                "learning_budget": 500.0,
                "operational_budget": 1100.0,
                "reserve_budget": 400.0,
                "spent_learning": 90.0,
                "spent_operational": 180.0,
            },
            flags_payload={
                "meta_live": False,
                "shopify_live": False,
                "dropi_live": False,
                "spend_real_money": False,
            },
        )

        scenarios["breaker_open"] = _run_scenario(
            repo_root=repo_root,
            name="breaker_open",
            ops_tick_payload=BREAKER_OPEN_OPS_TICK,
            vault_payload={
                "total_budget": 350.0,
                "learning_budget": 120.0,
                "operational_budget": 80.0,
                "reserve_budget": 40.0,
                "spent_learning": 115.0,
                "spent_operational": 78.0,
            },
            flags_payload={
                "meta_live": False,
                "shopify_live": False,
                "dropi_live": False,
                "spend_real_money": False,
            },
        )

    probe_total = len(probes)
    probe_ok_count = sum(1 for x in probes.values() if x.get("status") == "ok")
    scenario_total = len(scenarios)
    scenario_ok_count = sum(1 for x in scenarios.values() if x.get("status") == "ok")

    return {
        "CAPA_B_PASS": len(contract_errors) == 0 and probe_total == probe_ok_count and scenario_total == scenario_ok_count,
        "repo_root": str(repo_root),
        "contract_error_count": len(contract_errors),
        "probe_total": probe_total,
        "probe_ok_count": probe_ok_count,
        "scenario_total": scenario_total,
        "scenario_ok_count": scenario_ok_count,
        "imports": imports,
        "contract_errors": contract_errors,
        "probes": probes,
        "scenarios": scenarios,
    }


if __name__ == "__main__":
    print(json.dumps(run_all(), indent=2, ensure_ascii=False, sort_keys=True))
