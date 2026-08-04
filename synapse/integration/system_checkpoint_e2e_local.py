"""Truthful local-only commercial checkpoint compositor.

The checkpoint accepts only explicit operator files, composes the existing
catalog, Decimal finance, methodology, copy, custody, storefront, and local
Shopify draft authorities, then writes eleven deterministic operator artifacts.

It has no network, credential, live-action, publication, spend, fulfillment,
or order-forwarding surface.  Every persistent successful artifact is
confined to the explicit output directory, which must be outside the
repository.
"""

from __future__ import annotations

import argparse
import ctypes
import dataclasses
import hashlib
import hmac
import json
import os
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Any

from scripts.shopify_export_from_canonical import (
    SHOPIFY_DRAFT_CONTRACT_VERSION,
    build_shopify_draft_row,
    serialize_shopify_draft_export,
)
from synapse.financial.adapters import candidate_to_financial_input
from synapse.financial.evaluation import (
    Decision,
    FinancialAssumptions,
    FinancialInput,
    FinancialResult,
    ScenarioName,
    evaluate_financials,
)
from synapse.integration.canonical_product_bridge import (
    CUSTODY_SCHEMA_VERSION,
    SCHEMA_VERSION as CANONICAL_BRIDGE_SCHEMA_VERSION,
    canonicalize_local_product_candidate,
    local_product_candidate_sha256,
    promote_local_product_to_canonical_fixture,
    validate_local_product_promotion_approval,
    validate_promoted_fixture_custody,
)
from synapse.integration.local_catalog_to_methodology import (
    enrich_local_catalog_fixture_with_methodology,
)
from synapse.marketing_os.interrogation_engine import ComplianceEvaluator
from synapse.marketing_os.methodology_decision_engine import (
    EXPECTED_ENGINE_SCHEMA_VERSION,
)
from synapse.marketing_os.models import ProductContext
from synapse.ui.local_catalog_workspace import (
    INTAKE_SCHEMA_VERSION,
    STATUS_EVALUATING,
    CatalogIntakeError,
    parse_catalog_csv,
)
from synapse.ui.operator_workbench_renderer import scan_forbidden_tokens
from synapse.ui.operator_workbench_view_model import (
    SCHEMA_VERSION as WORKBENCH_SCHEMA_VERSION,
    build_view_model,
)
from synapse.ui.operator_workbench_visual import render_workspace_html
from synapse.ui.storefront_customer_copy import (
    SCHEMA_VERSION as CUSTOMER_COPY_SCHEMA_VERSION,
    canonicalize_customer_copy,
    customer_copy_sha256,
    validate_operator_approved_customer_copy,
)
from synapse.ui.storefront_read_model import (
    SCHEMA_VERSION as STOREFRONT_SCHEMA_VERSION,
    STATUS_READY,
    build_storefront_read_model,
    serialize_storefront_read_model,
)
from synapse.ui.system_checkpoint_report import (
    REPORT_SCHEMA_VERSION,
    render_system_checkpoint_report,
)


CHECKPOINT_SCHEMA_VERSION = "synapse.system_checkpoint_e2e_local.v1"
TRACE_SCHEMA_VERSION = "synapse.system_checkpoint_execution_trace.v1"
MANIFEST_SCHEMA_VERSION = "synapse.system_checkpoint_evidence_manifest.v1"
DECISION_RULE_VERSION = "CHECKPOINT_DECISION_ADAPTER_V1"
COPY_BINDING_VERSION = "CHECKPOINT_COPY_BINDING_V1"

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures"

ARTIFACT_FILENAMES: tuple[str, ...] = (
    "checkpoint_result.json",
    "execution_trace.json",
    "financial_result.json",
    "decision_record.json",
    "methodology_result.json",
    "canonical_product.json",
    "storefront_read_model.json",
    "shopify_draft_export.csv",
    "evidence_manifest.json",
    "checkpoint_report.html",
    "workspace.html",
)

BLOCKED_CAPABILITIES: tuple[str, ...] = (
    "network",
    "credential_loading",
    "shopify_api",
    "shopify_publication",
    "meta_transport",
    "dropi_transport",
    "order_forwarding",
    "external_write",
    "live_action",
    "spend",
    "fulfillment",
    "learning_loop",
)

SOURCE_IDENTITY_RELATIVE_PATHS: tuple[str, ...] = (
    "synapse/integration/system_checkpoint_e2e_local.py",
    "synapse/ui/system_checkpoint_report.py",
    "synapse/ui/local_catalog_workspace.py",
    "synapse/ui/operator_workbench_renderer.py",
    "synapse/ui/operator_workbench_view_model.py",
    "synapse/ui/operator_workbench_visual.py",
    "synapse/financial/adapters.py",
    "synapse/financial/evaluation.py",
    "synapse/integration/local_catalog_to_methodology.py",
    "synapse/marketing_os/interrogation_engine.py",
    "synapse/marketing_os/methodology_decision_engine.py",
    "synapse/marketing_os/models.py",
    "synapse/marketing_os/methodology_rule_loader.py",
    "synapse/marketing_os/methodology_rule_contract.py",
    "docs/phase1/A8_R101_MARKETING_METHOD_DEPTH_SPEC.json",
    "synapse/ui/storefront_customer_copy.py",
    "synapse/integration/canonical_product_bridge.py",
    "synapse/ui/storefront_read_model.py",
    "scripts/shopify_export_from_canonical.py",
)

_FINANCIAL_INPUT_FIELDS = frozenset(
    {"product_id", "estimated_cac", "expected_units"}
)
_REQUIRED_FINANCIAL_INPUT_FIELDS = frozenset(
    {"product_id", "estimated_cac"}
)
class SystemCheckpointError(ValueError):
    """Raised when the local checkpoint must fail closed."""


@dataclass(frozen=True, slots=True)
class SystemCheckpointInput:
    catalog_csv: str | Path
    product_id: str
    methodology_context_json: str | Path
    customer_copy_json: str | Path
    promotion_approval_json: str | Path
    copy_approval_json: str | Path
    financial_assumptions_json: str | Path | None
    output_dir: str | Path
    sample_input: bool = False


@dataclass(frozen=True, slots=True)
class SystemCheckpointResult:
    status: str
    product_id: str
    final_decision: str
    output_dir: Path
    artifact_sha256: Mapping[str, str]
    fixture_used: bool = False
    network_used: bool = False
    external_write: bool = False
    live_action: bool = False
    shopify_api_called: bool = False
    published: bool = False


def _json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _json_ready(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key.value if isinstance(key, Enum) else key): _json_ready(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [_json_ready(item) for item in value]
    return value


def _json_bytes(value: Any, *, pretty: bool = True) -> bytes:
    kwargs: dict[str, Any] = {
        "ensure_ascii": False,
        "sort_keys": True,
        "allow_nan": False,
    }
    if pretty:
        kwargs["indent"] = 2
    else:
        kwargs["separators"] = (",", ":")
    return (json.dumps(_json_ready(value), **kwargs) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest_value(value: Any) -> str:
    return _sha256_bytes(_json_bytes(value, pretty=False))


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _reject_remote_path(path: Path, label: str) -> None:
    raw = os.fspath(path)
    if raw.startswith(("\\\\", "//")):
        raise SystemCheckpointError(f"{label}_REMOTE_PATH_FORBIDDEN={raw}")
    if os.name != "nt":
        return
    anchor = path.anchor
    if not anchor:
        return
    try:
        drive_type = ctypes.windll.kernel32.GetDriveTypeW(str(anchor))
    except (AttributeError, OSError):
        raise SystemCheckpointError(
            f"{label}_DRIVE_TYPE_UNAVAILABLE={anchor}"
        ) from None
    if drive_type == 4:  # DRIVE_REMOTE
        raise SystemCheckpointError(
            f"{label}_REMOTE_DRIVE_FORBIDDEN={anchor}"
        )


def _reject_reparse_components(path: Path, label: str) -> None:
    """Reject symlink/junction traversal before resolving an operator path."""

    absolute = Path(os.path.abspath(os.fspath(path)))
    current = Path(absolute.anchor)
    parts = absolute.parts[1:] if absolute.anchor else absolute.parts
    for part in parts:
        current /= part
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            break
        except OSError as exc:
            raise SystemCheckpointError(
                f"{label}_PATH_COMPONENT_UNREADABLE="
                f"{current}:{exc.__class__.__name__}"
            ) from None
        file_attributes = getattr(metadata, "st_file_attributes", 0)
        if (
            stat.S_ISLNK(metadata.st_mode)
            or file_attributes
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        ):
            raise SystemCheckpointError(
                f"{label}_REPARSE_PATH_FORBIDDEN={current}"
            )


def _explicit_file(value: str | Path, label: str) -> Path:
    path = Path(value)
    _reject_remote_path(path, label)
    _reject_reparse_components(path, label)
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        raise SystemCheckpointError(f"{label}_FILE_NOT_FOUND={path}") from None
    _reject_remote_path(resolved, label)
    if not resolved.is_file():
        raise SystemCheckpointError(f"{label}_FILE_NOT_FOUND={resolved}")
    if _is_within(resolved, FIXTURE_ROOT):
        raise SystemCheckpointError(
            f"{label}_FIXTURE_PATH_FORBIDDEN={resolved}"
        )
    return resolved


def _load_json_mapping_bytes(value: bytes, label: str) -> dict[str, Any]:
    try:
        decoded = value.decode("utf-8")
        loaded = json.loads(decoded)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SystemCheckpointError(
            f"{label}_INVALID_JSON={exc.__class__.__name__}"
        ) from None
    if not isinstance(loaded, Mapping):
        raise SystemCheckpointError(f"{label}_MUST_BE_MAPPING")
    if any(not isinstance(key, str) for key in loaded):
        raise SystemCheckpointError(f"{label}_KEYS_MUST_BE_STRINGS")
    return dict(loaded)


def _finite_decimal(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise SystemCheckpointError(f"{label}_MUST_BE_FINITE_DECIMAL")
    try:
        parsed = (
            value if isinstance(value, Decimal) else Decimal(str(value).strip())
        )
    except (InvalidOperation, TypeError, ValueError):
        raise SystemCheckpointError(
            f"{label}_MUST_BE_FINITE_DECIMAL"
        ) from None
    if not parsed.is_finite():
        raise SystemCheckpointError(f"{label}_MUST_BE_FINITE_DECIMAL")
    return parsed


def _validate_customer_copy_compliance(
    customer_copy: Mapping[str, Any],
    methodology_context: Mapping[str, Any],
) -> None:
    """Fail closed on claims flagged by the existing compliance authority."""

    category = methodology_context.get("category")
    if not isinstance(category, str):
        raise SystemCheckpointError(
            "METHODOLOGY_CATEGORY_MUST_BE_STRING"
        )
    copy_text = "\n".join(
        (
            str(customer_copy["description"]),
            *[str(value) for value in customer_copy["facts"]],
            *[str(value) for value in customer_copy["proof"]],
        )
    )
    result = ComplianceEvaluator().evaluate(
        ProductContext(
            product_id=str(customer_copy["product_id"]),
            name=str(customer_copy["title"]),
            category=category,
            price=0.0,
            cost=0.0,
            description=copy_text,
        )
    )
    flags = result.findings.get("compliance_flags")
    if not isinstance(flags, list):
        raise SystemCheckpointError(
            "CUSTOMER_COPY_COMPLIANCE_AUTHORITY_INVALID"
        )
    if flags:
        categories = sorted(
            {
                str(flag).partition(":")[0]
                for flag in flags
                if str(flag).partition(":")[0]
            }
        )
        raise SystemCheckpointError(
            "CUSTOMER_COPY_COMPLIANCE_BLOCKED="
            + ",".join(categories)
        )


def _prepare_output_dir(value: str | Path) -> Path:
    raw = Path(value)
    _reject_remote_path(raw, "OUTPUT_DIR")
    _reject_reparse_components(raw, "OUTPUT_DIR")
    resolved = raw.resolve(strict=False)
    _reject_remote_path(resolved, "OUTPUT_DIR")
    if _is_within(resolved, REPO_ROOT):
        raise SystemCheckpointError(
            f"OUTPUT_DIR_INSIDE_REPOSITORY_FORBIDDEN={resolved}"
        )
    if os.path.lexists(resolved):
        raise SystemCheckpointError(
            f"OUTPUT_DIR_MUST_NOT_EXIST={resolved}"
        )
    if not resolved.parent.is_dir():
        raise SystemCheckpointError(
            f"OUTPUT_PARENT_MUST_EXIST={resolved.parent}"
        )
    return resolved


def _select_catalog_fixture(
    catalog_csv: Path,
    product_id: str,
) -> dict[str, Any]:
    selector = product_id.strip()
    if not selector:
        raise SystemCheckpointError("PRODUCT_ID_REQUIRED")
    try:
        intake = parse_catalog_csv(catalog_csv)
    except (CatalogIntakeError, InvalidOperation) as exc:
        raise SystemCheckpointError(f"CATALOG_INVALID={exc}") from None

    matching_rows = [
        row for row in intake.rows if row.product_id == selector
    ]
    matching_fixtures = [
        dict(fixture)
        for fixture in intake.fixtures
        if (
            isinstance(fixture.get("product"), Mapping)
            and fixture["product"].get("product_id") == selector
        )
    ]
    if not matching_rows:
        raise SystemCheckpointError(f"PRODUCT_ID_NOT_FOUND={selector}")
    if len(matching_rows) != 1 or len(matching_fixtures) != 1:
        raise SystemCheckpointError(
            f"PRODUCT_ID_AMBIGUOUS={selector}:"
            f"rows={len(matching_rows)}:fixtures={len(matching_fixtures)}"
        )
    if matching_rows[0].status != STATUS_EVALUATING:
        reasons = ",".join(matching_rows[0].reasons)
        raise SystemCheckpointError(
            f"PRODUCT_NOT_EVALUATABLE={selector}:"
            f"status={matching_rows[0].status}:reasons={reasons}"
        )
    fixture = matching_fixtures[0]
    if not isinstance(fixture.get("economics"), Mapping):
        raise SystemCheckpointError("CATALOG_ECONOMICS_REQUIRED")
    return fixture


@contextmanager
def _hold_catalog_stability_lock(catalog_csv: Path) -> Iterator[None]:
    """Prevent write/delete/rename while the path-based authority parses."""

    if os.name != "nt":
        raise SystemCheckpointError(
            "CATALOG_STABILITY_LOCK_UNAVAILABLE=non_windows_runtime"
        )

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = (
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
        )
        create_file.restype = ctypes.c_void_p
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = (ctypes.c_void_p,)
        close_handle.restype = ctypes.c_int
    except (AttributeError, OSError):
        raise SystemCheckpointError(
            "CATALOG_STABILITY_LOCK_UNAVAILABLE=win32_api"
        ) from None

    handle = create_file(
        str(catalog_csv),
        0x80000000,  # GENERIC_READ
        0x00000001,  # FILE_SHARE_READ; deny writes and delete/rename
        None,
        3,  # OPEN_EXISTING
        0x00000080,  # FILE_ATTRIBUTE_NORMAL
        None,
    )
    if handle in (None, ctypes.c_void_p(-1).value):
        raise SystemCheckpointError(
            "CATALOG_STABILITY_LOCK_UNAVAILABLE=acquire_failed"
        )
    try:
        yield
    finally:
        if close_handle(handle) == 0:
            raise SystemCheckpointError(
                "CATALOG_STABILITY_LOCK_RELEASE_FAILED"
            )


def _build_financial_input(
    fixture: Mapping[str, Any],
    financial_operator_input: Mapping[str, Any],
) -> tuple[FinancialInput, FinancialAssumptions]:
    keys = set(financial_operator_input)
    missing = sorted(_REQUIRED_FINANCIAL_INPUT_FIELDS - keys)
    unexpected = sorted(keys - _FINANCIAL_INPUT_FIELDS)
    if missing:
        raise SystemCheckpointError(
            "FINANCIAL_ASSUMPTIONS_MISSING_FIELDS=" + ",".join(missing)
        )
    if unexpected:
        raise SystemCheckpointError(
            "FINANCIAL_ASSUMPTIONS_UNEXPECTED_FIELDS="
            + ",".join(unexpected)
        )

    product = fixture.get("product")
    economics = fixture.get("economics")
    if not isinstance(product, Mapping) or not isinstance(economics, Mapping):
        raise SystemCheckpointError("NORMALIZED_PRODUCT_CONTRACT_INVALID")

    product_id = str(product.get("product_id", "")).strip()
    bound_product_id = financial_operator_input.get("product_id")
    if not isinstance(bound_product_id, str):
        raise SystemCheckpointError(
            "FINANCIAL_ASSUMPTIONS_PRODUCT_ID_MUST_BE_STRING"
        )
    if bound_product_id.strip() != product_id:
        raise SystemCheckpointError(
            "FINANCIAL_ASSUMPTIONS_PRODUCT_ID_MISMATCH"
        )

    product_cost = _finite_decimal(
        economics.get("product_cost_mxn"),
        "CATALOG_PRODUCT_COST",
    )
    shipping_cost = _finite_decimal(
        economics.get("shipping_cost_mxn"),
        "CATALOG_SHIPPING_COST",
    )
    payment_fee = _finite_decimal(
        economics.get("payment_fee_mxn"),
        "CATALOG_PAYMENT_FEE",
    )
    if product_cost < 0 or shipping_cost < 0 or payment_fee < 0:
        raise SystemCheckpointError(
            "CATALOG_NORMALIZED_COSTS_MUST_BE_NONNEGATIVE"
        )

    candidate: dict[str, Any] = {
        "product_id": product_id,
        "name": product.get("name"),
        "price": economics.get("price_mxn"),
        "landed_cost": product_cost + shipping_cost,
        "estimated_cac": financial_operator_input.get("estimated_cac"),
    }
    if "expected_units" in financial_operator_input:
        candidate["expected_units"] = financial_operator_input[
            "expected_units"
        ]

    try:
        financial_input = candidate_to_financial_input(candidate)
    except ValueError as exc:
        raise SystemCheckpointError(f"FINANCIAL_INPUT_INVALID={exc}") from None

    assumptions = FinancialAssumptions(
        payment_fee_pct=Decimal("0"),
        payment_fixed_fee=payment_fee,
    )
    return financial_input, assumptions


def build_checkpoint_decision_record(
    financial_result: FinancialResult,
) -> dict[str, Any]:
    """Map the canonical finance verdict without inventing a portfolio score."""

    mapping = {
        Decision.KILL: "REJECT",
        Decision.FAIL: "REJECT",
        Decision.WATCH: "NEEDS_EVIDENCE",
        Decision.PASS: "READY_FOR_REVIEW",
    }
    final_decision = mapping[financial_result.decision]
    result_payload = _json_ready(financial_result)
    run_basis = {
        "rule_version": DECISION_RULE_VERSION,
        "financial_result": result_payload,
    }
    run_id = f"checkpoint_{_digest_value(run_basis)[:24]}"
    return {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "rule_version": DECISION_RULE_VERSION,
        "run_id": run_id,
        "product_id": financial_result.product_id,
        "financial_decision": financial_result.decision.value,
        "final_decision": final_decision,
        "score": None,
        "score_authority": "none",
        "score_reason": (
            "No compatible scalar score authority exists for this local "
            "FinancialResult; the named rule mapping is the decision authority."
        ),
        "mapping": {
            "KILL": "REJECT",
            "FAIL": "REJECT",
            "WATCH": "NEEDS_EVIDENCE",
            "PASS": "READY_FOR_REVIEW",
            "TEST": "reserved_not_emitted",
        },
        "thresholds": _json_ready(financial_result.policy),
        "reason_codes": list(financial_result.reason_codes),
        "risk_flags": list(financial_result.risk_flags),
        "missing_evidence": (
            list(financial_result.risk_flags)
            if final_decision == "NEEDS_EVIDENCE"
            else []
        ),
        "portfolio_ranking_authority": False,
        "promotion_eligible": final_decision == "READY_FOR_REVIEW",
    }


def _build_checkpoint_workbench_fixture(
    *,
    catalog_csv: Path,
    checkpoint_input: SystemCheckpointInput,
    enriched_fixture: Mapping[str, Any],
    financial_result: FinancialResult,
    decision_record: Mapping[str, Any],
    methodology_context: Mapping[str, Any],
    methodology_result: Mapping[str, Any],
    canonical_copy: Mapping[str, Any],
    public_copy: Mapping[str, Any],
    canonical_product: Mapping[str, Any],
    custody: Mapping[str, Any],
    storefront_product: Mapping[str, Any],
    input_hashes: Mapping[str, str],
    copy_digest: str,
) -> dict[str, Any]:
    """Project validated checkpoint state into the existing Workbench fixture."""

    source_product = enriched_fixture.get("product")
    source_economics = enriched_fixture.get("economics")
    if not isinstance(source_product, Mapping):
        raise SystemCheckpointError("WORKBENCH_PRODUCT_CONTRACT_INVALID")
    if not isinstance(source_economics, Mapping):
        raise SystemCheckpointError("WORKBENCH_ECONOMICS_CONTRACT_INVALID")

    base = financial_result.scenarios.get(ScenarioName.BASE)
    if base is None:
        raise SystemCheckpointError("WORKBENCH_BASE_SCENARIO_REQUIRED")
    if base.price <= 0:
        raise SystemCheckpointError("WORKBENCH_BASE_PRICE_MUST_BE_POSITIVE")

    contribution_percent = (
        base.contribution_margin / base.price * Decimal("100")
    ).quantize(Decimal("0.01"))

    facts = [str(value) for value in canonical_copy.get("facts", ())]
    proof = [str(value) for value in canonical_copy.get("proof", ())]
    triggers = [str(value) for value in methodology_result.get("triggers", ())]
    risk_flags = [str(value) for value in financial_result.risk_flags]
    reason_codes = [str(value) for value in decision_record.get("reason_codes", ())]
    title = str(public_copy.get("title", "")).strip()
    description = str(public_copy.get("description", "")).strip()
    if not title or not description:
        raise SystemCheckpointError("WORKBENCH_APPROVED_COPY_REQUIRED")

    canonical_source_kind = str(canonical_product.get("source_kind", "")).strip()
    if not canonical_source_kind:
        raise SystemCheckpointError("WORKBENCH_CANONICAL_SOURCE_KIND_REQUIRED")

    storefront_price = storefront_product.get("price")
    if not isinstance(storefront_price, Mapping):
        raise SystemCheckpointError("WORKBENCH_STOREFRONT_PRICE_INVALID")

    proof_elements = list(methodology_context.get("proof_available", ()))
    market_context = (
        f"category={source_product.get('category', '')};"
        f"market={source_product.get('market', '')};"
        f"channel={methodology_context.get('channel', '')}"
    )

    claim_risk_by_copy = [
        {
            "copy_key": copy_key,
            "risk_level": "review",
            "risky_terms": [],
            "prohibited_terms": [
                "claims beyond the supplied facts and proof"
            ],
            "safe_rewrite": description if copy_key not in {"hooks", "headlines"} else title,
            "reason": (
                "Operator-approved local-preview copy only; "
                "publication is not authorized."
            ),
        }
        for copy_key in (
            "hooks",
            "headlines",
            "primary_texts",
            "short_ads",
            "long_ads",
        )
    ]

    code_head = _git_head()
    code_state = _git_source_state()

    safety_notes = [
        f"decision_run_id={decision_record['run_id']}",
        f"code_head={code_head}",
        "worktree_changes_present="
        f"{str(code_state['worktree_changes_present']).lower()}",
        f"catalog_csv_sha256={input_hashes['catalog_csv']}",
        f"customer_copy_sha256={copy_digest}",
        f"candidate_sha256={custody['candidate_sha256']}",
        f"approval_sha256={custody['approval_sha256']}",
        f"approval_record_id={custody['approval_record_id']}",
        f"sample_input={str(checkpoint_input.sample_input).lower()}",
        "commercial_evidence=false",
        "network_used=false",
        "external_write=false",
        "live_action=false",
        "publication_authorized=false",
        "shopify_api_called=false",
        "operator_in_control=true",
    ]

    return {
        "fixture_id": f"system_checkpoint_{source_product['product_id']}",
        "source_kind": "operator_local_catalog_import",
        "scenario": "system_checkpoint_e2e_local",
        "provenance": {
            "adapter_status": "system_checkpoint_projection_adapter",
            "base_head": code_head,
            "fase_1_status": "checkpoint_local_pending_external_audit",
            "island": "A8-R113.2",
            "worktree_state": (
                "dirty_source_hashes_required"
                if code_state["worktree_changes_present"]
                else "clean_head_identified"
            ),
        },
        "product": {
            "product_id": source_product["product_id"],
            "name": source_product["name"],
            "category": source_product.get("category", ""),
            "supplier": source_product.get("supplier", ""),
            "market": source_product.get("market", "MX"),
            "status": "checkpoint_ready_for_review",
        },
        "decision": {
            "outcome": "REVIEW_REQUIRED",
            "permission_gate": "REVIEW",
            "reason": (
                "Checkpoint local PASS: finanzas, metodologia, copy, custodia, "
                "storefront y Shopify draft fueron compuestos; la decision "
                "READY_FOR_REVIEW exige revision humana y no autoriza publicar."
            ),
            "reason_codes": reason_codes,
            "caveats": [
                *risk_flags,
                "READY_FOR_REVIEW is not commercial readiness.",
                "Publication and external writes remain unavailable.",
            ],
            "financial_decision": decision_record.get("financial_decision"),
            "final_decision": decision_record.get("final_decision"),
            "decision_run_id": decision_record.get("run_id"),
            "promotion_eligible": decision_record.get("promotion_eligible"),
            "canonical_source_kind": canonical_source_kind,
            "custody_status": "PASS",
        },
        "economics": {
            "currency": "MXN",
            "price_mxn": base.price,
            "product_cost_mxn": source_economics.get("product_cost_mxn"),
            "shipping_cost_mxn": source_economics.get("shipping_cost_mxn"),
            "payment_fee_mxn": source_economics.get("payment_fee_mxn"),
            "landed_cost_mxn": base.landed_cost,
            "gross_margin_mxn": base.gross_margin,
            "contribution_margin_mxn": base.contribution_margin,
            "contribution_margin_percent": contribution_percent,
            "breakeven_cpa_mxn": base.break_even_cac,
            "estimated_cac_mxn": base.estimated_cac,
            "notes": (
                "Canonical Decimal finance from the local checkpoint; "
                "operator-supplied estimated CAC; no market forecast."
            ),
        },
        "scores": {
            "score": None,
            "score_authority": "none",
            "score_reason": decision_record.get("score_reason"),
        },
        "operator_input": {
            "market_context": market_context,
            "proof_elements": proof_elements,
        },
        "claim_guard": {
            "allowed_claims": facts,
            "risky_claims": [],
            "prohibited_claims": [
                "claims beyond the supplied facts and proof"
            ],
            "safe_wording": [description],
            "claim_guard_summary": (
                "Only operator-approved local-preview facts and proof may be used."
            ),
        },
        "shopify": {
            "title": title,
            "subtitle": "",
            "short_description": description,
            "long_description": description,
            "bullets": facts,
            "benefits": [],
            "specifications": [],
            "faq": [],
            "seo_title": title,
            "seo_meta_description": description,
            "handle": storefront_product.get("slug", ""),
            "tags": [
                "shopify_mode=draft_export",
                "published=false",
                "external_write=false",
                "shopify_api_called=false",
            ],
            "category": storefront_product.get("category", ""),
            "shipping_note": "",
            "refund_claim_note": "",
            "claim_safe_disclaimer": (
                "Local preview only; publication is not authorized."
            ),
            "image_checklist": [],
            "publish_checklist": [
                "Review the approved local-preview copy.",
                "Resolve variants and assets before any future publication gate.",
                "Publication remains unavailable in this checkpoint.",
            ],
            "missing_inputs": [
                "variants_not_modeled",
                "publication_not_authorized",
            ],
        },
        "marketing": {
            "strategy_summary": methodology_result.get("safe_output", ""),
            "core_angle": methodology_result.get("safe_output", ""),
            "why_this_angle": (
                f"rule={methodology_result.get('selected_rule_id', '')}; "
                f"framework={methodology_result.get('selected_framework', '')}"
            ),
            "buyer_profile": methodology_context.get("buyer_state", ""),
            "audience": [],
            "hooks": [title],
            "headlines": [title],
            "primary_texts": [description],
            "short_ads": [description],
            "long_ads": [description],
            "captions": [description],
            "ugc_scripts": [],
            "video_scripts": [],
            "image_ad_concepts": proof or facts,
            "channel_packs": [],
            "testing_plan": {
                "phase_1": "Local operator review only.",
                "budget_note": "No spend is authorized.",
            },
            "angle_matrix": [],
            "creative_hypotheses": [],
            "claim_risk_by_copy": claim_risk_by_copy,
            "testing_plan_v2": {
                "success_signals": [],
                "warning_signals": risk_flags,
                "stop_signals": [
                    "Any claim beyond supplied facts and proof.",
                    "Any request for live publication or external writes.",
                ],
                "continue_if": [
                    "Operator confirms the local evidence and approved copy."
                ],
                "review_if": [
                    "Any input, approval digest, or custody record changes."
                ],
                "kill_if": [
                    "Custody, compliance, or publication boundaries fail."
                ],
                "what_not_to_conclude": [
                    "Do not conclude product-market fit or commercial readiness."
                ],
                "first_test_budget_boundary_dry_run_only": (
                    "No spend; local dry-run evidence only."
                ),
            },
        },
        "learning": {
            "hypotheses": triggers,
            "evidence_needed": proof,
            "first_sale_signals": [],
            "risk_signals": risk_flags,
            "continue_if": [
                "Operator confirms the local evidence and approved copy."
            ],
            "review_if": [
                "Any source input or approval digest changes."
            ],
            "kill_if": [
                "Custody, compliance, or safety boundaries fail."
            ],
            "operator_observations_schema": {"fields": []},
        },
        "blocked": [],
        "operator_actions": [
            {
                "action_id": "review_system_checkpoint_evidence",
                "label": "Revisar la evidencia del checkpoint.",
                "kind": "review_checkpoint",
                "target": "evidence",
                "notes": (
                    "READY_FOR_REVIEW is an operator gate, not a launch or "
                    "commercial-readiness claim."
                ),
            },
            {
                "action_id": "review_local_shopify_draft",
                "label": (
                    "Revisar el borrador local de Shopify; "
                    "la publicacion permanece no autorizada."
                ),
                "kind": "review_shopify_draft",
                "target": "shopify_studio",
                "notes": (
                    "The local draft is a preparation artifact only and does "
                    "not authorize publication or an external write."
                ),
            },
        ],
        "pipeline": {
            "source": "system_checkpoint_e2e_local",
            "total_candidates": 1,
            "current_candidate_rank": 1,
        },
        "evidence": {
            "notes": [
                f"Catalog source: {catalog_csv.name}.",
                f"Methodology rule: {methodology_result.get('selected_rule_id', '')}.",
                f"Methodology framework: {methodology_result.get('selected_framework', '')}.",
                f"Canonical source kind: {canonical_source_kind}.",
                f"Storefront preview status: {storefront_product.get('preview_status', '')}.",
                f"Storefront publication status: {storefront_product.get('publication_status', '')}.",
                *safety_notes,
            ],
            "artifacts": [
                "financial_result.json",
                "decision_record.json",
                "methodology_result.json",
                "canonical_product.json",
                "storefront_read_model.json",
                "shopify_draft_export.csv",
                "checkpoint_report.html",
                "workspace.html",
            ],
        },
    }


def _trace_step(
    *,
    step_name: str,
    input_contract: str,
    output_contract: str,
    source: str,
    execution: str,
    input_sha256: str | None = None,
    output_sha256: str | None = None,
    digest_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "step_name": step_name,
        "input_contract": input_contract,
        "output_contract": output_contract,
        "source_file_symbol": source,
        "status": "PASS",
        "execution": execution,
        "fixture_used": False,
        "external_write": False,
        "input_sha256": input_sha256,
        "output_sha256": output_sha256,
        "digest_reason": digest_reason,
        "blocking_reason": None,
    }


def _git_head() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise SystemCheckpointError(
            f"CODE_HEAD_UNAVAILABLE={exc.__class__.__name__}"
        ) from None
    head = completed.stdout.strip()
    if len(head) != 40:
        raise SystemCheckpointError("CODE_HEAD_INVALID")
    return head


def _git_source_state() -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [
                "git",
                "--no-optional-locks",
                "-c",
                "core.fsmonitor=false",
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise SystemCheckpointError(
            f"CODE_STATE_UNAVAILABLE={exc.__class__.__name__}"
        ) from None
    worktree_changes_present = bool(completed.stdout.strip())
    return {
        "head_fully_identifies_executed_source": False,
        "loaded_module_bytes_proven_by_source_hashes": False,
        "source_hash_semantics": (
            "on-disk bytes captured after module import and revalidated "
            "before artifact publication"
        ),
        "dirty_state_scope": "repository-wide porcelain status",
        "worktree_changes_present": worktree_changes_present,
        "execution_identity_requires_source_hashes": True,
    }


def _read_source_identity_bytes() -> dict[str, bytes]:
    values: dict[str, bytes] = {}
    for relative in SOURCE_IDENTITY_RELATIVE_PATHS:
        path = REPO_ROOT / relative
        try:
            values[relative] = path.read_bytes()
        except OSError as exc:
            raise SystemCheckpointError(
                f"SOURCE_IDENTITY_READ_FAILED={relative}:"
                f"{exc.__class__.__name__}"
            ) from None
    return values


def _assert_sources_unchanged(
    original_bytes: Mapping[str, bytes],
) -> None:
    for relative in SOURCE_IDENTITY_RELATIVE_PATHS:
        try:
            current = (REPO_ROOT / relative).read_bytes()
        except OSError as exc:
            raise SystemCheckpointError(
                f"SOURCE_CHANGED_DURING_RUN={relative}:"
                f"{exc.__class__.__name__}"
            ) from None
        if not hmac.compare_digest(current, original_bytes[relative]):
            raise SystemCheckpointError(
                f"SOURCE_CHANGED_DURING_RUN={relative}"
            )


def _write_artifacts(
    output_dir: Path,
    artifacts: Mapping[str, bytes],
) -> None:
    if set(artifacts) != set(ARTIFACT_FILENAMES):
        raise SystemCheckpointError("INTERNAL_ARTIFACT_SET_MISMATCH")
    _reject_remote_path(output_dir, "OUTPUT_DIR")
    _reject_reparse_components(output_dir, "OUTPUT_DIR")
    expected_root = output_dir.resolve(strict=False)
    if os.path.lexists(output_dir):
        raise SystemCheckpointError(
            f"OUTPUT_DIR_NO_LONGER_ABSENT={output_dir}"
        )
    if not output_dir.parent.is_dir():
        raise SystemCheckpointError(
            f"OUTPUT_PARENT_NO_LONGER_AVAILABLE={output_dir.parent}"
        )

    staging_dir: Path | None = None
    created_files: list[Path] = []
    staging_created = False
    try:
        staging_dir = Path(
            tempfile.mkdtemp(
                dir=output_dir.parent,
                prefix=f".{output_dir.name}.checkpoint-",
            )
        )
        staging_created = True
        _reject_reparse_components(staging_dir, "OUTPUT_STAGING")
        if staging_dir.resolve(strict=True).parent != expected_root.parent:
            raise SystemCheckpointError(
                f"OUTPUT_PARENT_CHANGED_BEFORE_WRITE={output_dir.parent}"
            )

        for filename in ARTIFACT_FILENAMES:
            target = staging_dir / filename
            with target.open("xb") as handle:
                created_files.append(target)
                handle.write(artifacts[filename])
                handle.flush()
                os.fsync(handle.fileno())

        if os.path.lexists(output_dir):
            raise SystemCheckpointError(
                f"OUTPUT_DIR_CREATED_DURING_RUN={output_dir}"
            )
        if set(path.name for path in staging_dir.iterdir()) != set(
            ARTIFACT_FILENAMES
        ):
            raise SystemCheckpointError("OUTPUT_STAGING_SET_MISMATCH")
        for filename in ARTIFACT_FILENAMES:
            try:
                staged_bytes = (staging_dir / filename).read_bytes()
            except OSError as exc:
                raise SystemCheckpointError(
                    f"OUTPUT_STAGING_READ_FAILED={filename}:"
                    f"{exc.__class__.__name__}"
                ) from None
            if not hmac.compare_digest(
                staged_bytes,
                artifacts[filename],
            ):
                raise SystemCheckpointError(
                    f"OUTPUT_STAGING_DIGEST_MISMATCH={filename}"
                )

        # On the official Windows runtime os.rename is an atomic,
        # no-overwrite directory publication.  All eleven files therefore
        # become visible as one set, or none of them do.
        staging_dir.rename(output_dir)
        staging_created = False
    except BaseException as exc:
        cleanup_failures: list[str] = []
        for path in reversed(created_files):
            try:
                path.unlink(missing_ok=True)
            except OSError as cleanup_exc:
                cleanup_failures.append(
                    f"{path.name}:{cleanup_exc.__class__.__name__}"
                )
        if (
            staging_created
            and staging_dir is not None
            and os.path.lexists(staging_dir)
        ):
            try:
                staging_dir.rmdir()
            except OSError as cleanup_exc:
                cleanup_failures.append(
                    f"{staging_dir.name}:"
                    f"{cleanup_exc.__class__.__name__}"
                )
        if cleanup_failures:
            raise SystemCheckpointError(
                "OUTPUT_CLEANUP_FAILED=" + ",".join(cleanup_failures)
            ) from None
        if isinstance(exc, SystemCheckpointError):
            raise
        if isinstance(exc, OSError):
            raise SystemCheckpointError(
                f"OUTPUT_WRITE_FAILED={exc.__class__.__name__}"
            ) from None
        raise


def _assert_inputs_unchanged(
    paths: Mapping[str, Path],
    original_bytes: Mapping[str, bytes],
) -> None:
    for name, path in paths.items():
        try:
            current = path.read_bytes()
        except OSError as exc:
            raise SystemCheckpointError(
                f"INPUT_CHANGED_DURING_RUN={name}:"
                f"{exc.__class__.__name__}"
            ) from None
        if not hmac.compare_digest(current, original_bytes[name]):
            raise SystemCheckpointError(
                f"INPUT_CHANGED_DURING_RUN={name}"
            )


def run_system_checkpoint(
    checkpoint_input: SystemCheckpointInput,
) -> SystemCheckpointResult:
    """Execute the complete deterministic local checkpoint."""

    if not isinstance(checkpoint_input, SystemCheckpointInput):
        raise SystemCheckpointError(
            "checkpoint_input must be a SystemCheckpointInput"
        )
    if not isinstance(checkpoint_input.sample_input, bool):
        raise SystemCheckpointError("sample_input must be a boolean")

    output_dir = _prepare_output_dir(checkpoint_input.output_dir)
    catalog_csv = _explicit_file(checkpoint_input.catalog_csv, "CATALOG")
    methodology_path = _explicit_file(
        checkpoint_input.methodology_context_json,
        "METHODOLOGY_CONTEXT",
    )
    customer_copy_path = _explicit_file(
        checkpoint_input.customer_copy_json,
        "CUSTOMER_COPY",
    )
    promotion_path = _explicit_file(
        checkpoint_input.promotion_approval_json,
        "PROMOTION_APPROVAL",
    )
    copy_approval_path = _explicit_file(
        checkpoint_input.copy_approval_json,
        "COPY_APPROVAL",
    )
    if checkpoint_input.financial_assumptions_json is None:
        raise SystemCheckpointError(
            "FINANCIAL_ASSUMPTIONS_REQUIRED="
            "explicit_product_bound_estimated_cac"
        )
    financial_path = _explicit_file(
        checkpoint_input.financial_assumptions_json,
        "FINANCIAL_ASSUMPTIONS",
    )

    input_paths = {
        "catalog_csv": catalog_csv,
        "financial_assumptions_json": financial_path,
        "methodology_context_json": methodology_path,
        "customer_copy_json": customer_copy_path,
        "promotion_approval_json": promotion_path,
        "copy_approval_json": copy_approval_path,
    }
    source_identity_bytes = _read_source_identity_bytes()
    with _hold_catalog_stability_lock(catalog_csv):
        try:
            input_bytes = {
                name: path.read_bytes()
                for name, path in input_paths.items()
            }
        except OSError as exc:
            raise SystemCheckpointError(
                f"INPUT_READ_FAILED={exc.__class__.__name__}"
            ) from None
        input_hashes = {
            name: _sha256_bytes(value)
            for name, value in input_bytes.items()
        }

        fixture = _select_catalog_fixture(
            catalog_csv,
            checkpoint_input.product_id,
        )
        _assert_inputs_unchanged(
            {"catalog_csv": catalog_csv},
            {"catalog_csv": input_bytes["catalog_csv"]},
        )
    product = fixture["product"]
    product_id = str(product["product_id"])
    normalized_digest = _digest_value(fixture)

    financial_operator_input = _load_json_mapping_bytes(
        input_bytes["financial_assumptions_json"],
        "FINANCIAL_ASSUMPTIONS",
    )
    financial_input, assumptions = _build_financial_input(
        fixture,
        financial_operator_input,
    )
    try:
        financial_result = evaluate_financials(
            financial_input,
            assumptions=assumptions,
        )
    except ValueError as exc:
        raise SystemCheckpointError(
            f"FINANCIAL_EVALUATION_INVALID={exc}"
        ) from None
    financial_artifact = _json_ready(financial_result)
    decision_record = build_checkpoint_decision_record(financial_result)
    if decision_record["final_decision"] != "READY_FOR_REVIEW":
        raise SystemCheckpointError(
            "FINANCIAL_DECISION_BLOCKED="
            f"{decision_record['final_decision']}:"
            f"{financial_result.decision.value}"
        )

    methodology_context = _load_json_mapping_bytes(
        input_bytes["methodology_context_json"],
        "METHODOLOGY_CONTEXT",
    )
    try:
        enriched_fixture = enrich_local_catalog_fixture_with_methodology(
            fixture,
            methodology_context,
        )
    except ValueError as exc:
        raise SystemCheckpointError(f"METHODOLOGY_INVALID={exc}") from None
    methodology_result = enriched_fixture["decision"]["methodology"]
    if (
        methodology_result.get("status") != "accepted"
        or methodology_result.get("operator_review_required") is not False
    ):
        raise SystemCheckpointError(
            "METHODOLOGY_BLOCKED="
            f"{methodology_result.get('status')}:"
            f"review={methodology_result.get('operator_review_required')}"
        )

    customer_copy = _load_json_mapping_bytes(
        input_bytes["customer_copy_json"],
        "CUSTOMER_COPY",
    )
    try:
        canonical_copy = canonicalize_customer_copy(
            customer_copy,
            expected_product_id=product_id,
        )
    except ValueError as exc:
        raise SystemCheckpointError(f"CUSTOMER_COPY_INVALID={exc}") from None
    _validate_customer_copy_compliance(
        canonical_copy,
        methodology_context,
    )

    candidate_output = methodology_context.get("candidate_output")
    if (
        not isinstance(candidate_output, str)
        or candidate_output.strip() != canonical_copy["description"]
    ):
        raise SystemCheckpointError(
            "CUSTOMER_COPY_DESCRIPTION_NOT_BOUND_TO_METHODOLOGY"
        )
    context_facts = methodology_context.get("product_facts")
    context_proof = methodology_context.get("proof_available")
    if not isinstance(context_facts, Sequence) or isinstance(
        context_facts, (str, bytes)
    ):
        raise SystemCheckpointError("METHODOLOGY_PRODUCT_FACTS_INVALID")
    if not isinstance(context_proof, Sequence) or isinstance(
        context_proof, (str, bytes)
    ):
        raise SystemCheckpointError("METHODOLOGY_PROOF_INVALID")
    if not set(canonical_copy["facts"]).issubset(set(context_facts)):
        raise SystemCheckpointError(
            "CUSTOMER_COPY_FACTS_NOT_BOUND_TO_METHODOLOGY"
        )
    if not set(canonical_copy["proof"]).issubset(set(context_proof)):
        raise SystemCheckpointError(
            "CUSTOMER_COPY_PROOF_NOT_BOUND_TO_METHODOLOGY"
        )
    copy_digest = customer_copy_sha256(canonical_copy)

    candidate_snapshot = canonicalize_local_product_candidate(
        enriched_fixture,
        financial_input,
    )
    candidate_digest = local_product_candidate_sha256(
        enriched_fixture,
        financial_input,
    )
    promotion_approval = _load_json_mapping_bytes(
        input_bytes["promotion_approval_json"],
        "PROMOTION_APPROVAL",
    )
    try:
        validated_promotion_approval = (
            validate_local_product_promotion_approval(
                promotion_approval,
                candidate_snapshot=candidate_snapshot,
                decision_run_id=decision_record["run_id"],
                financial_decision=decision_record[
                    "financial_decision"
                ],
                final_decision=decision_record["final_decision"],
            )
        )
    except ValueError as exc:
        raise SystemCheckpointError(
            f"PROMOTION_APPROVAL_INVALID={exc}"
        ) from None

    copy_approval = _load_json_mapping_bytes(
        input_bytes["copy_approval_json"],
        "COPY_APPROVAL",
    )
    copy_envelope = {
        "copy": canonical_copy,
        "approval": copy_approval,
    }
    try:
        public_copy = validate_operator_approved_customer_copy(
            copy_envelope,
            expected_product_id=product_id,
        )
    except ValueError as exc:
        raise SystemCheckpointError(
            f"COPY_APPROVAL_INVALID={exc}"
        ) from None

    try:
        canonical_product = promote_local_product_to_canonical_fixture(
            catalog_fixture=enriched_fixture,
            financial_input=financial_input,
            financial_result=financial_result,
            decision_record=decision_record,
            approval=promotion_approval,
        )
        custody = validate_promoted_fixture_custody(canonical_product)
    except ValueError as exc:
        raise SystemCheckpointError(
            f"CANONICAL_PROMOTION_INVALID={exc}"
        ) from None
    if not hmac.compare_digest(
        str(custody["candidate_sha256"]),
        candidate_digest,
    ):
        raise SystemCheckpointError("CANONICAL_CUSTODY_DIGEST_MISMATCH")

    try:
        storefront = build_storefront_read_model(
            [
                {
                    "fixture": canonical_product,
                    "methodology_context": methodology_context,
                    "customer_copy_approval": copy_envelope,
                }
            ]
        )
    except ValueError as exc:
        raise SystemCheckpointError(f"STOREFRONT_INVALID={exc}") from None
    if len(storefront.get("products", [])) != 1:
        raise SystemCheckpointError("STOREFRONT_PRODUCT_COUNT_MISMATCH")
    storefront_product = storefront["products"][0]
    if storefront_product.get("preview_status") != STATUS_READY:
        raise SystemCheckpointError(
            "STOREFRONT_NOT_READY_FOR_LOCAL_PREVIEW"
        )
    if storefront_product.get("publication_status") != "NOT_AUTHORIZED":
        raise SystemCheckpointError(
            "STOREFRONT_PUBLICATION_BOUNDARY_INVALID"
        )

    try:
        shopify_row = build_shopify_draft_row(
            product_id=product_id,
            expected_product_id=product_id,
            title=public_copy["title"],
            price_mxn=storefront_product["price"]["amount"],
            description=public_copy["description"],
            category=storefront_product["category"],
            handle=storefront_product["slug"],
            tags=(),
        )
        shopify_csv = serialize_shopify_draft_export(shopify_row)
    except ValueError as exc:
        raise SystemCheckpointError(
            f"SHOPIFY_DRAFT_INVALID={exc}"
        ) from None

    financial_bytes = _json_bytes(financial_artifact)
    decision_bytes = _json_bytes(decision_record)
    methodology_artifact = {
        "schema_version": EXPECTED_ENGINE_SCHEMA_VERSION,
        "context_sha256": input_hashes["methodology_context_json"],
        "operator_context_supplied": True,
        "decision": methodology_result,
    }
    methodology_bytes = _json_bytes(methodology_artifact)
    canonical_bytes = _json_bytes(canonical_product)
    storefront_bytes = serialize_storefront_read_model(storefront).encode(
        "utf-8"
    )
    shopify_bytes = shopify_csv.encode("utf-8")

    try:
        workbench_fixture = _json_ready(
            _build_checkpoint_workbench_fixture(
                catalog_csv=catalog_csv,
                checkpoint_input=checkpoint_input,
                enriched_fixture=enriched_fixture,
                financial_result=financial_result,
                decision_record=decision_record,
                methodology_context=methodology_context,
                methodology_result=methodology_result,
                canonical_copy=canonical_copy,
                public_copy=public_copy,
                canonical_product=canonical_product,
                custody=custody,
                storefront_product=storefront_product,
                input_hashes=input_hashes,
                copy_digest=copy_digest,
            )
        )
        workbench_view_model = build_view_model(
            workbench_fixture,
            source_fixture=f"{catalog_csv.name}#{product_id}",
        )
        workspace_html = render_workspace_html([workbench_view_model])
    except ValueError as exc:
        raise SystemCheckpointError(f"WORKBENCH_INVALID={exc}") from None
    workspace_forbidden = scan_forbidden_tokens(workspace_html)
    if workspace_forbidden:
        raise SystemCheckpointError(
            "WORKBENCH_FORBIDDEN_TOKENS=" + ",".join(workspace_forbidden)
        )
    workspace_bytes = workspace_html.encode("utf-8")

    manual_steps = [
        "catalog_csv",
        "financial_assumptions_json",
        "methodology_context_json",
        "customer_copy_json",
        "promotion_approval_json",
        "copy_approval_json",
    ]
    automatic_steps = [
        "strict_product_normalization",
        "canonical_decimal_financial_evaluation",
        "checkpoint_decision_adapter",
        "methodology_enrichment",
        "customer_copy_validation",
        "customer_copy_methodology_binding",
        "promotion_approval_validation",
        "customer_copy_approval_validation",
        "canonical_product_promotion_and_custody",
        "storefront_read_model",
        "shopify_draft_export",
        "operator_workbench",
        "evidence_manifest",
        "operator_html_report",
    ]

    checkpoint_result_artifact = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "status": "PASS",
        "product_id": product_id,
        "final_decision": decision_record["final_decision"],
        "sample_input": checkpoint_input.sample_input,
        "commercial_evidence": False,
        "fixture_used": False,
        "offline_only": True,
        "network_used": False,
        "external_write": False,
        "live_action": False,
        "shopify": {
            "shopify_mode": "draft_export",
            "published": False,
            "external_write": False,
            "shopify_api_called": False,
            "operator_publication_approval": False,
        },
        "manual_steps": manual_steps,
        "automatic_steps": automatic_steps,
        "blocked_capabilities": list(BLOCKED_CAPABILITIES),
        "artifacts": list(ARTIFACT_FILENAMES),
    }
    checkpoint_bytes = _json_bytes(checkpoint_result_artifact)

    trace_steps = [
        _trace_step(
            step_name="catalog_input",
            input_contract="explicit local CSV file",
            output_contract=INTAKE_SCHEMA_VERSION,
            source=(
                "synapse.ui.local_catalog_workspace.parse_catalog_csv"
            ),
            execution="manual",
            input_sha256=input_hashes["catalog_csv"],
            output_sha256=normalized_digest,
        ),
        _trace_step(
            step_name="strict_product_normalization",
            input_contract=INTAKE_SCHEMA_VERSION,
            output_contract="one unambiguous EVALUATING catalog fixture",
            source=(
                "synapse.integration.system_checkpoint_e2e_local."
                "_select_catalog_fixture"
            ),
            execution="automatic",
            input_sha256=input_hashes["catalog_csv"],
            output_sha256=normalized_digest,
        ),
        _trace_step(
            step_name="financial_operator_input",
            input_contract="product-bound estimated_cac JSON",
            output_contract="synapse.financial.evaluation.FinancialInput",
            source=(
                "synapse.financial.adapters."
                "candidate_to_financial_input"
            ),
            execution="manual",
            input_sha256=input_hashes["financial_assumptions_json"],
            output_sha256=_digest_value(financial_input),
        ),
        _trace_step(
            step_name="financial_evaluation",
            input_contract="FinancialInput + FinancialAssumptions",
            output_contract="synapse.financial.evaluation.FinancialResult",
            source="synapse.financial.evaluation.evaluate_financials",
            execution="automatic",
            output_sha256=_sha256_bytes(financial_bytes),
        ),
        _trace_step(
            step_name="checkpoint_decision",
            input_contract="canonical FinancialResult",
            output_contract=DECISION_RULE_VERSION,
            source=(
                "synapse.integration.system_checkpoint_e2e_local."
                "build_checkpoint_decision_record"
            ),
            execution="automatic",
            output_sha256=_sha256_bytes(decision_bytes),
        ),
        _trace_step(
            step_name="methodology_context",
            input_contract="explicit operator methodology JSON",
            output_contract="validated explicit methodology context",
            source=(
                "synapse.integration.system_checkpoint_e2e_local."
                "_load_json_mapping_bytes"
            ),
            execution="manual",
            input_sha256=input_hashes["methodology_context_json"],
            output_sha256=_digest_value(methodology_context),
        ),
        _trace_step(
            step_name="methodology_enrichment",
            input_contract="local fixture + explicit methodology context",
            output_contract=EXPECTED_ENGINE_SCHEMA_VERSION,
            source=(
                "synapse.integration.local_catalog_to_methodology."
                "enrich_local_catalog_fixture_with_methodology"
            ),
            execution="automatic",
            input_sha256=input_hashes["methodology_context_json"],
            output_sha256=_sha256_bytes(methodology_bytes),
        ),
        _trace_step(
            step_name="customer_copy",
            input_contract="explicit operator customer-copy JSON",
            output_contract=CUSTOMER_COPY_SCHEMA_VERSION,
            source=(
                "synapse.integration.system_checkpoint_e2e_local."
                "_load_json_mapping_bytes"
            ),
            execution="manual",
            input_sha256=input_hashes["customer_copy_json"],
            output_sha256=_digest_value(customer_copy),
        ),
        _trace_step(
            step_name="customer_copy_validation",
            input_contract=(
                "operator customer copy + existing compliance authority"
            ),
            output_contract=CUSTOMER_COPY_SCHEMA_VERSION,
            source=(
                "synapse.ui.storefront_customer_copy."
                "canonicalize_customer_copy + "
                "synapse.marketing_os.interrogation_engine."
                "ComplianceEvaluator.evaluate"
            ),
            execution="automatic",
            input_sha256=input_hashes["customer_copy_json"],
            output_sha256=copy_digest,
        ),
        _trace_step(
            step_name="customer_copy_methodology_binding",
            input_contract=(
                "canonical customer copy + explicit methodology context"
            ),
            output_contract=COPY_BINDING_VERSION,
            source=(
                "synapse.integration.system_checkpoint_e2e_local."
                "run_system_checkpoint"
            ),
            execution="automatic",
            input_sha256=copy_digest,
            output_sha256=_digest_value(
                {
                    "description": canonical_copy["description"],
                    "facts": canonical_copy["facts"],
                    "proof": canonical_copy["proof"],
                    "methodology_context_sha256": input_hashes[
                        "methodology_context_json"
                    ],
                }
            ),
        ),
        _trace_step(
            step_name="promotion_approval",
            input_contract="explicit digest-bound promotion approval JSON",
            output_contract="operator promotion approval mapping",
            source=(
                "synapse.integration.system_checkpoint_e2e_local."
                "_load_json_mapping_bytes"
            ),
            execution="manual",
            input_sha256=input_hashes["promotion_approval_json"],
            output_sha256=_digest_value(promotion_approval),
        ),
        _trace_step(
            step_name="promotion_approval_validation",
            input_contract="candidate and decision-bound promotion approval",
            output_contract=CANONICAL_BRIDGE_SCHEMA_VERSION,
            source=(
                "synapse.integration.canonical_product_bridge."
                "validate_local_product_promotion_approval"
            ),
            execution="automatic",
            input_sha256=input_hashes["promotion_approval_json"],
            output_sha256=_digest_value(
                validated_promotion_approval
            ),
        ),
        _trace_step(
            step_name="customer_copy_approval",
            input_contract="explicit digest-bound copy approval JSON",
            output_contract="operator customer-copy approval mapping",
            source=(
                "synapse.integration.system_checkpoint_e2e_local."
                "_load_json_mapping_bytes"
            ),
            execution="manual",
            input_sha256=input_hashes["copy_approval_json"],
            output_sha256=_digest_value(copy_approval),
        ),
        _trace_step(
            step_name="customer_copy_approval_validation",
            input_contract="copy digest-bound local-preview approval",
            output_contract=CUSTOMER_COPY_SCHEMA_VERSION,
            source=(
                "synapse.ui.storefront_customer_copy."
                "validate_operator_approved_customer_copy"
            ),
            execution="automatic",
            input_sha256=input_hashes["copy_approval_json"],
            output_sha256=copy_digest,
        ),
        _trace_step(
            step_name="canonical_product_promotion",
            input_contract=(
                "approved local fixture + FinancialResult + decision"
            ),
            output_contract=CUSTODY_SCHEMA_VERSION,
            source=(
                "synapse.integration.canonical_product_bridge."
                "promote_local_product_to_canonical_fixture"
            ),
            execution="automatic",
            output_sha256=_sha256_bytes(canonical_bytes),
        ),
        _trace_step(
            step_name="storefront_read_model",
            input_contract="custody-validated canonical local product",
            output_contract=STOREFRONT_SCHEMA_VERSION,
            source=(
                "synapse.ui.storefront_read_model."
                "build_storefront_read_model"
            ),
            execution="automatic",
            output_sha256=_sha256_bytes(storefront_bytes),
        ),
        _trace_step(
            step_name="shopify_draft_export",
            input_contract="approved storefront public projection",
            output_contract=SHOPIFY_DRAFT_CONTRACT_VERSION,
            source=(
                "scripts.shopify_export_from_canonical."
                "build_shopify_draft_row"
            ),
            execution="automatic",
            output_sha256=_sha256_bytes(shopify_bytes),
        ),
        _trace_step(
            step_name="operator_workbench",
            input_contract="validated checkpoint projections",
            output_contract=WORKBENCH_SCHEMA_VERSION,
            source=(
                "synapse.ui.operator_workbench_visual."
                "render_workspace_html"
            ),
            execution="automatic",
            output_sha256=_sha256_bytes(workspace_bytes),
        ),
        _trace_step(
            step_name="evidence_manifest",
            input_contract="input/output digests and contract versions",
            output_contract=MANIFEST_SCHEMA_VERSION,
            source=(
                "synapse.integration.system_checkpoint_e2e_local."
                "run_system_checkpoint"
            ),
            execution="automatic",
            digest_reason="manifest self-hash is recorded as manifest_basis_sha256",
        ),
        _trace_step(
            step_name="operator_html_report",
            input_contract="validated checkpoint projections",
            output_contract=REPORT_SCHEMA_VERSION,
            source=(
                "synapse.ui.system_checkpoint_report."
                "render_system_checkpoint_report"
            ),
            execution="automatic",
            digest_reason="report digest is recorded in evidence_manifest.json",
        ),
    ]
    execution_trace = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "status": "PASS",
        "fixture_used": False,
        "external_write": False,
        "steps": trace_steps,
    }
    trace_bytes = _json_bytes(execution_trace)

    base_scenario = financial_result.scenarios[ScenarioName.BASE]
    report_data = {
        "sample_input": checkpoint_input.sample_input,
        "commercial_evidence": False,
        "offline_only": True,
        "external_write": False,
        "live_action": False,
        "published": False,
        "product": {
            "source": str(catalog_csv),
            "source_sha256": input_hashes["catalog_csv"],
            "product_id": product_id,
            "title": product["name"],
            "supplier_facts": {
                "supplier": product["supplier"],
                "category": product["category"],
                "market": product["market"],
            },
        },
        "financial": {
            "authority": "synapse.financial.evaluation.evaluate_financials",
            "selling_price_mxn": format(base_scenario.price, "f"),
            "landed_cost_mxn": format(base_scenario.landed_cost, "f"),
            "gross_margin_mxn": format(base_scenario.gross_margin, "f"),
            "break_even_cpa_mxn": format(
                base_scenario.break_even_cac,
                "f",
            ),
            "contribution_margin_mxn": format(
                base_scenario.contribution_margin,
                "f",
            ),
            "decision": financial_result.decision.value,
            "warnings": list(financial_result.risk_flags),
            "scenarios": financial_artifact["scenarios"],
        },
        "decision": decision_record,
        "methodology": {
            "buyer": methodology_context["buyer_state"],
            "problem": {
                "status": "not_explicitly_supplied",
                "derived": False,
            },
            "product_facts": list(
                methodology_context["product_facts"]
            ),
            "angle": {
                "rule": methodology_result["selected_rule_id"],
                "framework": methodology_result["selected_framework"],
                "safe_operator_output": methodology_result["safe_output"],
            },
            "proof": list(methodology_context["proof_available"]),
            "allowed_claims": {
                "scope": "operator_approved_local_preview_copy_facts_only",
                "publication_authorized": False,
                "items": list(canonical_copy["facts"]),
            },
            "blocked_claims": [
                "claims beyond the supplied facts and proof"
            ],
            "methodology_triggers": list(
                methodology_result.get("triggers", [])
            ),
        },
        "customer_copy": {
            "supplied_manually": True,
            "validation_status": "PASS",
            "compliance_authority": (
                "synapse.marketing_os.interrogation_engine."
                "ComplianceEvaluator.evaluate"
            ),
            "binding_contract": COPY_BINDING_VERSION,
            "approval_status": copy_approval.get("status"),
            "sha256": copy_digest,
            "public_projection": public_copy,
        },
        "canonical_product": {
            "canonical_id": custody["candidate_id"],
            "source_kind": canonical_product["source_kind"],
            "candidate_sha256": custody["candidate_sha256"],
            "approval_sha256": custody["approval_sha256"],
            "approval_record_id": custody["approval_record_id"],
            "custody_status": "PASS",
        },
        "storefront_read_model": {
            "title": storefront_product["public_content"]["title"],
            "benefits": {
                "source": "operator_approved_customer_copy.facts",
                "generated": False,
                "items": storefront_product["public_content"]["facts"],
            },
            "price": storefront_product["price"],
            "variants": {
                "state": "not_modeled_in_storefront_read_model",
                "items": [],
            },
            "preview_status": storefront_product["preview_status"],
            "publication_status": storefront_product[
                "publication_status"
            ],
            "safety": storefront["safety"],
        },
        "shopify_boundary": {
            "shopify_mode": "draft_export",
            "draft_export_prepared": True,
            "published": False,
            "external_write": False,
            "shopify_api_called": False,
            "operator_publication_approval": False,
            "shopify_default_option": "Default Title",
            "operator_action_required": (
                "Review the local CSV; publication remains unavailable."
            ),
        },
        "execution_trace": execution_trace["steps"],
    }
    report_html = render_system_checkpoint_report(report_data)
    report_bytes = report_html.encode("utf-8")

    pre_manifest_artifacts: dict[str, bytes] = {
        "checkpoint_result.json": checkpoint_bytes,
        "execution_trace.json": trace_bytes,
        "financial_result.json": financial_bytes,
        "decision_record.json": decision_bytes,
        "methodology_result.json": methodology_bytes,
        "canonical_product.json": canonical_bytes,
        "storefront_read_model.json": storefront_bytes,
        "shopify_draft_export.csv": shopify_bytes,
        "checkpoint_report.html": report_bytes,
        "workspace.html": workspace_bytes,
    }
    output_hashes = {
        filename: _sha256_bytes(content)
        for filename, content in pre_manifest_artifacts.items()
    }
    code_head = _git_head()
    code_state = _git_source_state()
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "code_head": code_head,
        "code_identity": {
            **code_state,
            "source_file_sha256": {
                relative: _sha256_bytes(value)
                for relative, value in source_identity_bytes.items()
            },
        },
        "input_files": {
            name: {
                "path": str(path),
                "sha256": input_hashes[name],
                "manual": True,
                "contract": (
                    "product-bound estimated CAC evidence; not an "
                    "engine-assumption override"
                    if name == "financial_assumptions_json"
                    else "explicit operator local file"
                ),
            }
            for name, path in input_paths.items()
        },
        "output_files": {
            filename: {"sha256": digest}
            for filename, digest in sorted(output_hashes.items())
        },
        "self_hash_in_output_files": False,
        "contracts": {
            "checkpoint": CHECKPOINT_SCHEMA_VERSION,
            "catalog": INTAKE_SCHEMA_VERSION,
            "financial": "synapse.financial.evaluation.FinancialResult",
            "decision": DECISION_RULE_VERSION,
            "methodology": EXPECTED_ENGINE_SCHEMA_VERSION,
            "customer_copy": CUSTOMER_COPY_SCHEMA_VERSION,
            "customer_copy_binding": COPY_BINDING_VERSION,
            "canonical_bridge": CANONICAL_BRIDGE_SCHEMA_VERSION,
            "canonical_custody": CUSTODY_SCHEMA_VERSION,
            "storefront": STOREFRONT_SCHEMA_VERSION,
            "shopify_draft": SHOPIFY_DRAFT_CONTRACT_VERSION,
            "operator_workbench": WORKBENCH_SCHEMA_VERSION,
            "report": REPORT_SCHEMA_VERSION,
        },
        "authorities": {
            "catalog": (
                "synapse.ui.local_catalog_workspace.parse_catalog_csv"
            ),
            "financial": (
                "synapse.financial.evaluation.evaluate_financials"
            ),
            "methodology": (
                "synapse.integration.local_catalog_to_methodology."
                "enrich_local_catalog_fixture_with_methodology"
            ),
            "customer_copy": (
                "synapse.ui.storefront_customer_copy."
                "validate_operator_approved_customer_copy"
            ),
            "customer_copy_claim_safety": (
                "synapse.marketing_os.interrogation_engine."
                "ComplianceEvaluator.evaluate"
            ),
            "canonical_product": (
                "synapse.integration.canonical_product_bridge."
                "promote_local_product_to_canonical_fixture"
            ),
            "storefront": (
                "synapse.ui.storefront_read_model."
                "build_storefront_read_model"
            ),
            "shopify_draft": (
                "scripts.shopify_export_from_canonical."
                "build_shopify_draft_row"
            ),
            "operator_workbench_view_model": (
                "synapse.ui.operator_workbench_view_model.build_view_model"
            ),
            "operator_workbench": (
                "synapse.ui.operator_workbench_visual.render_workspace_html"
            ),
        },
        "sample_input": checkpoint_input.sample_input,
        "commercial_evidence": False,
        "fixture_used": False,
        "network_used": False,
        "external_write": False,
        "live_action": False,
        "publication_authorized": False,
        "shopify_api_called": False,
        "final_decision": decision_record["final_decision"],
        "blocked_capabilities": list(BLOCKED_CAPABILITIES),
        "warnings": [
            "This checkpoint is local evidence, not live readiness.",
            "The operator supplied estimated CAC; no CAC was inferred.",
            (
                "Catalog payment_fee_mxn is mapped to the canonical engine "
                "fixed fee with payment_fee_pct=0."
            ),
            (
                "The --financial-assumptions-json filename is a mandated "
                "CLI compatibility name; its v1 payload is product-bound "
                "CAC evidence, not a general engine-assumption override."
            ),
            (
                "No compatible scalar score authority exists; the named "
                "checkpoint decision rule is recorded instead."
            ),
            (
                "READY_FOR_REVIEW remains an operator review gate; it does "
                "not authorize publication or claim commercial readiness."
            ),
        ]
        + (
            ["Sample input is not commercial evidence."]
            if checkpoint_input.sample_input
            else []
        ),
    }
    manifest["manifest_basis_sha256"] = _digest_value(manifest)
    manifest_bytes = _json_bytes(manifest)

    artifacts = {
        **pre_manifest_artifacts,
        "evidence_manifest.json": manifest_bytes,
    }
    _assert_inputs_unchanged(input_paths, input_bytes)
    _assert_sources_unchanged(source_identity_bytes)
    _write_artifacts(output_dir, artifacts)

    artifact_sha256 = {
        filename: _sha256_bytes(content)
        for filename, content in artifacts.items()
    }
    return SystemCheckpointResult(
        status="PASS",
        product_id=product_id,
        final_decision=decision_record["final_decision"],
        output_dir=output_dir,
        artifact_sha256=artifact_sha256,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m synapse.integration.system_checkpoint_e2e_local",
        description=(
            "Run the deterministic local-only SYNAPSE system checkpoint."
        ),
        allow_abbrev=False,
    )
    parser.add_argument("--catalog-csv", required=True)
    parser.add_argument("--product-id", required=True)
    parser.add_argument("--methodology-context-json", required=True)
    parser.add_argument("--customer-copy-json", required=True)
    parser.add_argument("--promotion-approval-json", required=True)
    parser.add_argument("--copy-approval-json", required=True)
    parser.add_argument(
        "--financial-assumptions-json",
        help=(
            "Optional CLI path; a successful full checkpoint currently "
            "requires its explicit product-bound estimated CAC because "
            "the local catalog contract intentionally has no CAC."
        ),
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--sample-input",
        action="store_true",
        help="Label an explicit sample run; never commercial evidence.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = run_system_checkpoint(
            SystemCheckpointInput(
                catalog_csv=args.catalog_csv,
                product_id=args.product_id,
                methodology_context_json=args.methodology_context_json,
                customer_copy_json=args.customer_copy_json,
                promotion_approval_json=args.promotion_approval_json,
                copy_approval_json=args.copy_approval_json,
                financial_assumptions_json=args.financial_assumptions_json,
                output_dir=args.output_dir,
                sample_input=args.sample_input,
            )
        )
    except (SystemCheckpointError, ValueError) as exc:
        print(
            f"SYSTEM_CHECKPOINT_ERROR={exc.__class__.__name__}:{exc}",
            file=sys.stderr,
        )
        return 2

    print("SYSTEM_CHECKPOINT_STATUS=PASS")
    print(f"PRODUCT_ID={result.product_id}")
    print(f"FINAL_DECISION={result.final_decision}")
    print(f"OUTPUT_DIR={result.output_dir}")
    print("FIXTURE_USED=false")
    print("NETWORK_USED=false")
    print("EXTERNAL_WRITE=false")
    print("LIVE_ACTION=false")
    print("SHOPIFY_API_CALLED=false")
    print("PUBLISHED=false")
    return 0


__all__ = [
    "ARTIFACT_FILENAMES",
    "BLOCKED_CAPABILITIES",
    "CHECKPOINT_SCHEMA_VERSION",
    "COPY_BINDING_VERSION",
    "DECISION_RULE_VERSION",
    "SystemCheckpointError",
    "SystemCheckpointInput",
    "SystemCheckpointResult",
    "build_checkpoint_decision_record",
    "main",
    "run_system_checkpoint",
]


if __name__ == "__main__":
    raise SystemExit(main())
