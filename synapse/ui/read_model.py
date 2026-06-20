"""Read-only Streamlit viewer for existing SYNAPSE run artifacts.

Scope:
- Reads existing files under runs/operacion_cli_dia1/.
- Displays scenario, decision, safety, creative hooks, and ledger invariants.
- Does not execute simulations.
- Does not write files.
- Does not call network APIs.
"""

from __future__ import annotations
from synapse.cli._blacklist import GENERIC_BLACKLIST as NPC_BLACKLIST_PATTERNS

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from synapse.ui._shopify_fixture_schema import (
    validate_shopify_ops_fixture,
    validate_shopify_products_fixture,
)

MAX_RUN_DIRS_DISPLAYED = 8


EXPECTED_RUNTIME_PRODUCT_COUNT = MAX_RUN_DIRS_DISPLAYED


def build_run_inventory_status(
    run_count: int,
    expected_count: int = EXPECTED_RUNTIME_PRODUCT_COUNT,
) -> dict[str, object]:
    """Build a side-effect-free runtime inventory status for the read-only UI."""

    observed_count = int(run_count)
    expected = int(expected_count)

    if observed_count < 0:
        raise ValueError("run_count must be >= 0")
    if expected < 0:
        raise ValueError("expected_count must be >= 0")

    displayed_count = min(observed_count, expected)
    hidden_count = max(observed_count - expected, 0)
    missing_count = max(expected - observed_count, 0)

    if observed_count == 0:
        state = "empty"
        message = f"No runtime products detected. Expected {expected}."
        should_warn = True
    elif observed_count < expected:
        state = "partial"
        message = f"Runtime inventory partial: {observed_count}/{expected} products detected."
        should_warn = True
    elif observed_count == expected:
        state = "complete"
        message = f"Runtime inventory complete: {observed_count}/{expected}."
        should_warn = False
    else:
        state = "overflow"
        message = f"Runtime inventory overflow: showing {displayed_count}/{expected}, hidden={hidden_count}."
        should_warn = True

    return {
        "observed_count": observed_count,
        "expected_count": expected,
        "displayed_count": displayed_count,
        "hidden_count": hidden_count,
        "missing_count": missing_count,
        "inventory_label": f"{displayed_count}/{expected}",
        "state": state,
        "message": message,
        "should_warn": should_warn,
    }

RUNS_DIR = Path("runs/operacion_cli_dia1")
PREFERRED_RUN_ROOT = Path("runs/operacion_cli_dia1") / "operacion_cli_dia1"
FALLBACK_RUN_ROOT = Path("runs/operacion_cli_dia1") / "a8_r54k_gate_false_green_fix" / "known_cases_runtime"

FEEDBACK_SIGNAL_FILE = "feedback_signal.json"

REQUIRED_FILES = (
    "scenario.json",
    "decision.json",
    "safety_posture.json",
    "creative_pack.json",
    "ledger_sandbox.ndjson",
)

LEDGER_INVARIANT_KEYS = (
    "external_mutation",
    "spend_count",
    "shopify_write_count",
    "meta_write_count",
    "dropi_write_count",
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SHOPIFY_PRODUCTS_FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "capa_b" / "products_nominal.json"
SHOPIFY_OPS_TICK_FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "capa_b" / "ops_tick_nominal.json"

SHOPIFY_READ_ONLY_FLAG_KEYS = (
    "shopify_live",
    "spend_real_money",
)

SHOPIFY_PRODUCT_ROW_KEYS = (
    "product_id",
    "title",
    "category",
    "price",
    "cost",
    "margin_percent",
    "sales",
    "supplier",
    "source",
)

@dataclass(frozen=True)
class ProductRun:
    """A complete read-only product run."""

    path: Path
    scenario: Mapping[str, Any]
    decision: Mapping[str, Any]
    safety: Mapping[str, Any]
    creative: Mapping[str, Any]
    ledger_rows: Sequence[Mapping[str, Any]]
    feedback_signal: Mapping[str, Any] = field(default_factory=dict)

    @property
    def product_name(self) -> str:
        return as_text(self.scenario.get("product_name"), fallback=self.path.parent.name)

    @property
    def score(self) -> float:
        return as_float(self.decision.get("score"))

    @property
    def threshold(self) -> float:
        return as_float(self.decision.get("threshold"))

    @property
    def permission_gate(self) -> str:
        return as_text(self.decision.get("permission_gate"), fallback="UNKNOWN")

    @property
    def final_outcome(self) -> str:
        return as_text(self.decision.get("final_outcome"), fallback="UNKNOWN")

    @property
    def feedback_status(self) -> str:
        return as_text(
            self.feedback_signal.get("signal_status") or self.feedback_signal.get("status"),
            fallback="UNKNOWN",
        )

    @property
    def feedback_recommendation(self) -> str:
        return as_text(self.feedback_signal.get("recommendation"), fallback="UNKNOWN")

    @property
    def feedback_reason_codes(self) -> list[Any]:
        return as_list(self.feedback_signal.get("reason_codes"))


@dataclass(frozen=True)
class ShopifyReadOnlySnapshot:
    """Local, read-only Shopify snapshot loaded from fixtures."""

    products: Sequence[Mapping[str, Any]]
    ops_tick: Mapping[str, Any]
    product_source: Path
    ops_source: Path

    @property
    def flags(self) -> Mapping[str, Any]:
        flags = self.ops_tick.get("flags")
        return flags if isinstance(flags, dict) else {}

    @property
    def shopify_health(self) -> Mapping[str, Any]:
        shopify = self.ops_tick.get("shopify")
        return shopify if isinstance(shopify, dict) else {}

    @property
    def product_count(self) -> int:
        return len(self.products)

    @property
    def shopify_live_enabled(self) -> bool:
        return bool(self.flags.get("shopify_live", False))

    @property
    def spend_real_money_enabled(self) -> bool:
        return bool(self.flags.get("spend_real_money", False))


def as_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def read_json(path: Path) -> Mapping[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def read_ndjson(path: Path) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        item = json.loads(line)
        if isinstance(item, dict):
            rows.append(item)
    return rows


def is_complete_run_dir(path: Path) -> bool:
    return path.is_dir() and all((path / filename).is_file() for filename in REQUIRED_FILES)


def discover_roots() -> list[Path]:
    roots: list[Path] = []
    if PREFERRED_RUN_ROOT.is_dir():
        roots.append(PREFERRED_RUN_ROOT)
    if FALLBACK_RUN_ROOT.is_dir():
        roots.append(FALLBACK_RUN_ROOT)
    if RUNS_DIR.is_dir() and not roots:
        roots.append(RUNS_DIR)
    return roots


def discover_run_dirs(root: Path | None = None) -> list[Path]:
    search_roots = [root] if root is not None else discover_roots()
    run_dirs: list[Path] = []
    for search_root in search_roots:
        for scenario_path in sorted(search_root.rglob("scenario.json")):
            candidate = scenario_path.parent
            if is_complete_run_dir(candidate):
                run_dirs.append(candidate)

    deduped = sorted(set(run_dirs), key=lambda item: str(item))
    return deduped[:MAX_RUN_DIRS_DISPLAYED]


def load_product_run(path: Path) -> ProductRun:
    return ProductRun(
        path=path,
        scenario=read_json(path / "scenario.json"),
        decision=read_json(path / "decision.json"),
        safety=read_json(path / "safety_posture.json"),
        creative=read_json(path / "creative_pack.json"),
        ledger_rows=read_ndjson(path / "ledger.ndjson"),
        feedback_signal=read_json_object_if_exists(path / FEEDBACK_SIGNAL_FILE),
    )


def load_product_runs() -> list[ProductRun]:
    return [load_product_run(path) for path in discover_run_dirs()]


def read_json_list(path: Path) -> list[Mapping[str, Any]]:
    if not path.is_file():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON fixture: {path}") from exc

    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array: {path}")

    return [item for item in data if isinstance(item, dict)]


def read_json_object_if_exists(path: Path) -> Mapping[str, Any]:
    if not path.is_file():
        return {}

    try:
        return read_json(path)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON fixture: {path}") from exc


def load_shopify_read_only_snapshot(
    products_path: Path = SHOPIFY_PRODUCTS_FIXTURE_PATH,
    ops_path: Path = SHOPIFY_OPS_TICK_FIXTURE_PATH,
) -> ShopifyReadOnlySnapshot:
    """Load and validate a Shopify-like local snapshot without live API access."""
    products = validate_shopify_products_fixture(read_json_list(products_path), products_path)
    ops_tick = validate_shopify_ops_fixture(read_json_object_if_exists(ops_path), ops_path)

    return ShopifyReadOnlySnapshot(
        products=products,
        ops_tick=ops_tick,
        product_source=products_path,
        ops_source=ops_path,
    )


def shopify_guardrail_rows(snapshot: ShopifyReadOnlySnapshot) -> list[dict[str, Any]]:
    flags = snapshot.flags
    health = snapshot.shopify_health

    return [
        {
            "guardrail": "source_mode",
            "value": "local_fixture_only",
            "expected": "local_fixture_only",
            "ok": True,
        },
        {
            "guardrail": "shopify_live",
            "value": bool(flags.get("shopify_live", False)),
            "expected": False,
            "ok": bool(flags.get("shopify_live", False)) is False,
        },
        {
            "guardrail": "spend_real_money",
            "value": bool(flags.get("spend_real_money", False)),
            "expected": False,
            "ok": bool(flags.get("spend_real_money", False)) is False,
        },
        {
            "guardrail": "shopify_api_ok",
            "value": health.get("api_ok", "N/A"),
            "expected": "observational_only",
            "ok": True,
        },
        {
            "guardrail": "orders_last_hour",
            "value": health.get("orders_last_hour", "N/A"),
            "expected": "read_only_metric",
            "ok": True,
        },
    ]


def shopify_product_rows(snapshot: ShopifyReadOnlySnapshot) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for product in snapshot.products:
        row = {
            "product_id": product.get("product_id", "N/A"),
            "title": product.get("title", "N/A"),
            "category": product.get("category", "N/A"),
            "price": product.get("price", "N/A"),
            "cost": product.get("cost", "N/A"),
            "margin_percent": product.get("margin_percent", "N/A"),
            "sales": product.get("sales", "N/A"),
            "supplier": product.get("supplier_name", "N/A"),
            "source": "local_fixture",
        }
        rows.append({key: row[key] for key in SHOPIFY_PRODUCT_ROW_KEYS})

    return rows


def matches_npc_template(text: str) -> bool:
    lowered = text.casefold()
    return any(pattern.casefold() in lowered for pattern in NPC_BLACKLIST_PATTERNS)


def label_for_run(run: ProductRun) -> str:
    return (
        f"{run.product_name} | score={run.score:g} | "
        f"gate={run.permission_gate} | outcome={run.final_outcome}"
    )


def ratio(score: float, threshold: float) -> float:
    if threshold <= 0:
        return 0.0
    return max(0.0, min(score / threshold, 1.0))


def render_table(st: Any, rows: Iterable[Mapping[str, Any]]) -> None:
    materialized = list(rows)
    if not materialized:
        st.info("Sin registros disponibles.")
        return
    st.dataframe(materialized, use_container_width=True)


def render_main_summary(st: Any, runs: Sequence[ProductRun]) -> None:
    st.subheader("Productos detectados")

    summary_rows = [
        {
            "producto": run.product_name,
            "score": run.score,
            "threshold": run.threshold,
            "permission_gate": run.permission_gate,
            "final_outcome": run.final_outcome,
            "run_dir": str(run.path),
        }
        for run in runs
    ]
    render_table(st, summary_rows)


def render_scenario(st: Any, run: ProductRun) -> None:
    st.subheader("Scenario")

    col_a, col_b = st.columns(2)
    with col_a:
        st.write(f"**Producto:** {as_text(run.scenario.get('product_name'), 'N/A')}")
        st.write(f"**Categoría:** {as_text(run.scenario.get('category'), 'N/A')}")
        st.write(f"**Precio propuesto:** {run.scenario.get('proposed_price_mxn', 'N/A')}")
        st.write(f"**Costo estimado:** {run.scenario.get('estimated_landed_cost_mxn', 'N/A')}")
    with col_b:
        st.write(f"**Audiencia:** {as_text(run.scenario.get('target_audience'), 'N/A')}")
        st.write(f"**Mercado:** {as_text(run.scenario.get('market'), 'N/A')}")
        st.write(f"**Ángulo:** {as_text(run.scenario.get('marketing_angle'), 'N/A')}")
        st.write(f"**Hook primario:** {as_text(run.scenario.get('primary_hook'), 'N/A')}")


def render_decision(st: Any, run: ProductRun) -> None:
    st.subheader("Decision")

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Score", f"{run.score:g}")
    col_b.metric("Threshold", f"{run.threshold:g}")
    col_c.metric("Outcome", run.final_outcome)

    st.progress(ratio(run.score, run.threshold))
    st.write(f"**Permission gate:** `{run.permission_gate}`")
    st.write(f"**Reason:** {as_text(run.decision.get('reason'), 'N/A')}")


def render_safety(st: Any, run: ProductRun) -> None:
    st.subheader("Safety posture")

    claim_safety = as_text(run.safety.get("claim_safety"), "UNKNOWN")
    categories = [as_text(item) for item in as_list(run.safety.get("claim_safety_categories")) if as_text(item)]

    st.write(f"**Claim safety:** `{claim_safety}`")

    if categories:
        st.warning("Claim safety categories visibles: " + ", ".join(categories))
        for category in categories:
            st.code(category, language=None)
    else:
        st.success("Sin categorías de claim safety reportadas.")


def render_hooks(st: Any, run: ProductRun) -> None:
    st.subheader("Hook variants")

    hooks = as_list(run.creative.get("hook_variants"))
    if not hooks:
        st.info("Sin hook_variants disponibles.")
        return

    for index, raw_hook in enumerate(hooks, start=1):
        hook = as_text(raw_hook, fallback="N/A")
        flag = " [NPC_TEMPLATE]" if matches_npc_template(hook) else ""
        st.write(f"{index}. {hook}{flag}")


def render_shopify_read_only_snapshot(st: Any, snapshot: ShopifyReadOnlySnapshot) -> None:
    st.subheader("Shopify read-only snapshot")
    st.caption(
        "Fuente local de fixtures. No llama Shopify live, no escribe archivos, no ejecuta mutations."
    )

    if not snapshot.products and not snapshot.ops_tick:
        st.info("Sin snapshot local de Shopify disponible.")
        return

    st.write(f"**Products fixture:** `{snapshot.product_source}`")
    st.write(f"**Ops fixture:** `{snapshot.ops_source}`")
    st.write(f"**Productos en snapshot:** {snapshot.product_count}")

    if snapshot.shopify_live_enabled or snapshot.spend_real_money_enabled:
        st.warning("Flags live/spend detectados en fixture local. Revisar antes de avanzar.")
    else:
        st.success("Guardrails Shopify locales en modo read-only.")

    st.write("**Guardrails**")
    render_table(st, shopify_guardrail_rows(snapshot))

    st.write("**Productos Shopify-like detectados**")
    render_table(st, shopify_product_rows(snapshot))


def render_shopify_read_only_snapshot_panel(
    st: Any,
    products_path: Path = SHOPIFY_PRODUCTS_FIXTURE_PATH,
    ops_path: Path = SHOPIFY_OPS_TICK_FIXTURE_PATH,
) -> None:
    try:
        snapshot = load_shopify_read_only_snapshot(products_path, ops_path)
    except (OSError, ValueError) as exc:
        st.warning(f"Shopify read-only snapshot no disponible: {exc}")
        return

    render_shopify_read_only_snapshot(st, snapshot)


def render_ledger(st: Any, run: ProductRun) -> None:
    st.subheader("Ledger sandbox invariants")

    invariant_rows: list[dict[str, Any]] = []
    for row_index, row in enumerate(run.ledger_rows, start=1):
        invariant_row: dict[str, Any] = {"row": row_index}
        for key in LEDGER_INVARIANT_KEYS:
            invariant_row[key] = row.get(key, "N/A")
        invariant_rows.append(invariant_row)

    render_table(st, invariant_rows)


def run_app() -> None:
    try:
        import streamlit as st
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Streamlit is required to run this viewer. Install requirements first."
        ) from exc

    st.set_page_config(page_title="SYNAPSE Read Model", layout="wide")
    st.title("SYNAPSE — Read-only local model viewer")
    st.caption("Lee evidencia existente en runs/operacion_cli_dia1/. No ejecuta simulaciones. No escribe archivos.")

    runs = load_product_runs()
    inventory_status = build_run_inventory_status(len(runs))
    st.caption(
        f"Run inventory: {inventory_status['inventory_label']} "
        f"| state={inventory_status['state']} "
        f"| observed={inventory_status['observed_count']} "
        f"| hidden={inventory_status['hidden_count']}"
    )
    if inventory_status["should_warn"]:
        st.warning(str(inventory_status["message"]))

    if not runs:
        st.error("No se encontraron runs completos en runs/operacion_cli_dia1/.")
        return

    render_main_summary(st, runs)
    st.divider()
    render_shopify_read_only_snapshot_panel(st)

    selected_label = st.selectbox(
        "Selecciona producto",
        options=[label_for_run(run) for run in runs],
        index=0,
    )
    selected_index = [label_for_run(run) for run in runs].index(selected_label)
    selected_run = runs[selected_index]

    st.divider()
    st.header(selected_run.product_name)
    st.caption(str(selected_run.path))

    render_scenario(st, selected_run)
    st.divider()
    render_decision(st, selected_run)
    st.divider()
    render_safety(st, selected_run)
    st.divider()
    render_hooks(st, selected_run)
    st.divider()
    render_ledger(st, selected_run)


if __name__ == "__main__":
    run_app()

# A8-R88I2 — First Selling Pack artifact read-only surface.
FIRST_SELLING_PACK_ARTIFACT_SCHEMA_VERSION = "a8-r88.first_selling_pack_artifact.v1"
FIRST_SELLING_PACK_ARTIFACT_LIMIT = 8


def _a8_r88_read_json(path):
    import json
    from pathlib import Path

    return json.loads(Path(path).read_text(encoding="utf-8"))


def is_first_selling_pack_artifact_dir(path) -> bool:
    """Return True when path looks like a persisted A8-R88 operator artifact.

    Read-only by design: this function does not write, publish, spend, or call
    external connectors.
    """
    from pathlib import Path

    root = Path(path)
    manifest_path = root / "manifest.json"
    first_pack_path = root / "first_selling_pack.json"
    operator_review_path = root / "operator_review.md"

    if not root.is_dir():
        return False
    if not manifest_path.is_file():
        return False
    if not first_pack_path.is_file():
        return False
    if not operator_review_path.is_file():
        return False

    try:
        manifest = _a8_r88_read_json(manifest_path)
    except Exception:
        return False

    return (
        manifest.get("schema_version") == FIRST_SELLING_PACK_ARTIFACT_SCHEMA_VERSION
        and manifest.get("artifact_type") == "first_selling_pack_operator_artifact"
    )


def discover_first_selling_pack_artifact_dirs(root=None):
    """Discover local FirstSellingPack artifact dirs, newest last.

    Read-only. It only scans files under root.
    """
    from pathlib import Path

    search_root = Path(root) if root is not None else Path("runs")
    if not search_root.exists():
        return []

    artifact_dirs = []
    for manifest_path in sorted(search_root.rglob("manifest.json")):
        candidate = manifest_path.parent
        if is_first_selling_pack_artifact_dir(candidate):
            artifact_dirs.append(candidate)

    return sorted(set(artifact_dirs), key=lambda item: str(item))[-FIRST_SELLING_PACK_ARTIFACT_LIMIT:]


def load_first_selling_pack_artifact(path):
    """Load one A8-R88 FirstSellingPack artifact into a JSON-ready dict."""
    from pathlib import Path

    root = Path(path)
    if not is_first_selling_pack_artifact_dir(root):
        raise ValueError(f"Not a FirstSellingPack artifact dir: {root}")

    manifest = _a8_r88_read_json(root / "manifest.json")
    pack = _a8_r88_read_json(root / "first_selling_pack.json")

    marketing_brief_path = root / "marketing_brief.json"
    expert_pack_path = root / "expert_pack.json"
    decision_path = root / "decision.json"
    scenario_path = root / "scenario.json"
    burnin_path = root / "burnin_summary.json"

    loaded = {
        "path": str(root),
        "run_dir": str(root),
        "run_id": str(manifest.get("run_id", "")),
        "schema_version": manifest.get("schema_version"),
        "artifact_type": manifest.get("artifact_type"),
        "product_id": manifest.get("product_id"),
        "product_name": manifest.get("product_name"),
        "boundaries": list(manifest.get("boundaries") or []),
        "manifest": manifest,
        "first_selling_pack": pack,
        "ready_for_operator_review": bool(pack.get("ready_for_operator_review")),
        "warnings": list(pack.get("warnings") or []),
        "platform": (
            pack.get("expert_pack", {})
            .get("campaign", {})
            .get("platform", "unknown")
        ),
        "adset_count": len(
            pack.get("expert_pack", {})
            .get("campaign", {})
            .get("adsets", [])
        ),
        "ad_count": sum(
            len(adset.get("ads", []))
            for adset in (
                pack.get("expert_pack", {})
                .get("campaign", {})
                .get("adsets", [])
            )
        ),
    }

    if marketing_brief_path.is_file():
        loaded["marketing_brief"] = _a8_r88_read_json(marketing_brief_path)
    if expert_pack_path.is_file():
        loaded["expert_pack"] = _a8_r88_read_json(expert_pack_path)
    if decision_path.is_file():
        loaded["decision"] = _a8_r88_read_json(decision_path)
    if scenario_path.is_file():
        loaded["scenario"] = _a8_r88_read_json(scenario_path)
    if burnin_path.is_file():
        loaded["burnin_summary"] = _a8_r88_read_json(burnin_path)

    return loaded


def load_first_selling_pack_artifacts(root=None):
    """Load discovered FirstSellingPack artifacts, newest last."""
    return [
        load_first_selling_pack_artifact(path)
        for path in discover_first_selling_pack_artifact_dirs(root)
    ]


def build_first_selling_pack_artifact_inventory(root=None):
    """Build read-only operator inventory for persisted FirstSellingPack artifacts."""
    artifacts = load_first_selling_pack_artifacts(root)
    latest = artifacts[-1] if artifacts else None

    return {
        "schema_version": "a8-r88.first_selling_pack_artifact_inventory.v1",
        "artifact_count": len(artifacts),
        "visible_artifact_count": len(artifacts),
        "latest_artifact_dir": latest["path"] if latest else "N/A",
        "latest_run_id": latest["run_id"] if latest else "N/A",
        "artifacts": artifacts,
        "read_only": True,
        "external_side_effects": False,
        "boundaries": [
            "dry_run_only",
            "operator_in_control",
            "no_live_writes",
            "no_automatic_spend",
            "no_fulfillment_automation",
            "claims_require_operator_review",
            "local_artifact_only",
            "operator_review_required",
        ],
    }