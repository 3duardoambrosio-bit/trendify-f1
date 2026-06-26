from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from synapse.integration.dropi_catalog_import_readonly import (
    DropiCatalogImportRecord,
    parse_dropi_catalog_csv,
)
from synapse.integration.dropi_to_financial_evaluation import (
    evaluate_dropi_candidate_financials,
)


MONEY_QUANT = Decimal("0.01")
PCT_QUANT = Decimal("0.0001")


@dataclass(frozen=True)
class DropiCatalogEvaluationAssumptions:
    sale_price_mxn: Decimal
    estimated_cac_mxn: Decimal
    expected_units: int
    min_margin_mxn: Decimal | None = None
    min_margin_pct: Decimal | None = None


@dataclass(frozen=True)
class DropiCatalogEvaluationItem:
    sku: str
    name: str
    supplier: str
    source_row_number: int
    accepted: bool
    reject_reason: str | None
    sale_price_mxn: Decimal
    estimated_cac_mxn: Decimal
    expected_units: int
    landed_cost_mxn: Decimal
    contribution_margin_mxn: Decimal
    contribution_margin_pct: Decimal
    financial_decision: str
    financial_reason_codes: tuple[str, ...]
    financial_payload: Mapping[str, Any]


@dataclass(frozen=True)
class DropiCatalogEvaluationResult:
    source: str
    source_record_count: int
    accepted_count: int
    rejected_count: int
    assumptions: DropiCatalogEvaluationAssumptions
    items: tuple[DropiCatalogEvaluationItem, ...]


class DropiCatalogEvaluationError(ValueError):
    pass


def _fail(reason: str) -> None:
    raise DropiCatalogEvaluationError(reason)


def _reject_float(value: Any, field: str) -> None:
    if isinstance(value, float):
        _fail(f"float_money_not_allowed:{field}")


def _to_decimal(value: Any, field: str) -> Decimal:
    _reject_float(value, field)

    if isinstance(value, Decimal):
        decimal_value = value
    elif isinstance(value, int):
        decimal_value = Decimal(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            _fail(f"missing_decimal:{field}")
        try:
            decimal_value = Decimal(stripped)
        except InvalidOperation:
            _fail(f"invalid_decimal:{field}")
    else:
        _fail(f"invalid_decimal_type:{field}:{type(value).__name__}")

    if not decimal_value.is_finite():
        _fail(f"non_finite_decimal:{field}")

    return decimal_value.quantize(MONEY_QUANT)


def _to_pct_decimal(value: Any, field: str) -> Decimal:
    _reject_float(value, field)

    if isinstance(value, Decimal):
        decimal_value = value
    elif isinstance(value, int):
        decimal_value = Decimal(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            _fail(f"missing_decimal:{field}")
        try:
            decimal_value = Decimal(stripped)
        except InvalidOperation:
            _fail(f"invalid_decimal:{field}")
    else:
        _fail(f"invalid_decimal_type:{field}:{type(value).__name__}")

    if not decimal_value.is_finite():
        _fail(f"non_finite_decimal:{field}")

    return decimal_value.quantize(PCT_QUANT)


def _to_expected_units(value: Any) -> int:
    if isinstance(value, bool):
        _fail("invalid_expected_units:bool")
    if isinstance(value, float):
        _fail("float_not_allowed:expected_units")
    if isinstance(value, int):
        units = value
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            _fail("missing_expected_units")
        if not stripped.isdigit():
            _fail("invalid_expected_units")
        units = int(stripped)
    else:
        _fail(f"invalid_expected_units_type:{type(value).__name__}")

    if units <= 0:
        _fail("expected_units_must_be_positive")

    return units


def build_dropi_catalog_evaluation_assumptions(
    *,
    sale_price_mxn: Any,
    estimated_cac_mxn: Any,
    expected_units: Any,
    min_margin_mxn: Any | None = None,
    min_margin_pct: Any | None = None,
) -> DropiCatalogEvaluationAssumptions:
    sale_price = _to_decimal(sale_price_mxn, "sale_price_mxn")
    estimated_cac = _to_decimal(estimated_cac_mxn, "estimated_cac_mxn")
    units = _to_expected_units(expected_units)

    if sale_price <= Decimal("0.00"):
        _fail("sale_price_mxn_must_be_positive")
    if estimated_cac < Decimal("0.00"):
        _fail("estimated_cac_mxn_must_be_non_negative")

    has_min_margin_mxn = min_margin_mxn is not None
    has_min_margin_pct = min_margin_pct is not None

    if has_min_margin_mxn == has_min_margin_pct:
        _fail("exactly_one_margin_threshold_required")

    parsed_min_margin_mxn = None
    parsed_min_margin_pct = None

    if has_min_margin_mxn:
        parsed_min_margin_mxn = _to_decimal(min_margin_mxn, "min_margin_mxn")
        if parsed_min_margin_mxn < Decimal("0.00"):
            _fail("min_margin_mxn_must_be_non_negative")

    if has_min_margin_pct:
        parsed_min_margin_pct = _to_pct_decimal(min_margin_pct, "min_margin_pct")
        if parsed_min_margin_pct < Decimal("0.0000"):
            _fail("min_margin_pct_must_be_non_negative")

    return DropiCatalogEvaluationAssumptions(
        sale_price_mxn=sale_price,
        estimated_cac_mxn=estimated_cac,
        expected_units=units,
        min_margin_mxn=parsed_min_margin_mxn,
        min_margin_pct=parsed_min_margin_pct,
    )


def _field(record: Any, name: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(name, default)
    return getattr(record, name, default)


def _record_to_candidate(record: DropiCatalogImportRecord) -> dict[str, Any]:
    sku = str(_field(record, "sku", "")).strip()
    name = str(_field(record, "name", "") or _field(record, "title", "")).strip()
    supplier = str(_field(record, "supplier", "")).strip()
    stock = _field(record, "stock", 0)
    source_row_number = _field(record, "source_row_number", 0)

    if not sku:
        _fail("missing_record_sku")
    if not name:
        _fail("missing_record_name")
    if not supplier:
        _fail("missing_record_supplier")

    landed_cost = _to_decimal(_field(record, "landed_cost_mxn", None), "landed_cost_mxn")
    supplier_cost = _to_decimal(_field(record, "supplier_cost_mxn", None), "supplier_cost_mxn")
    shipping_cost = _to_decimal(_field(record, "shipping_cost_mxn", None), "shipping_cost_mxn")

    if landed_cost < Decimal("0.00"):
        _fail("landed_cost_mxn_must_be_non_negative")
    if supplier_cost < Decimal("0.00"):
        _fail("supplier_cost_mxn_must_be_non_negative")
    if shipping_cost < Decimal("0.00"):
        _fail("shipping_cost_mxn_must_be_non_negative")

    return {
        "sku": sku,
        "product_id": sku,
        "id": sku,
        "name": name,
        "title": name,
        "supplier": supplier,
        "source_row_number": int(source_row_number),
        "stock": int(stock),
        "landed_cost": landed_cost,
        "landed_cost_mxn": landed_cost,
        "supplier_cost_mxn": supplier_cost,
        "shipping_cost_mxn": shipping_cost,
        "brand": str(_field(record, "brand", "") or ""),
        "category": str(_field(record, "category", "") or ""),
        "product_url": str(_field(record, "product_url", "") or ""),
        "image_url": str(_field(record, "image_url", "") or ""),
        "shipping_days": _field(record, "shipping_days", None),
        "supplier_rating": _field(record, "supplier_rating", None),
        "weight_kg": _field(record, "weight_kg", None),
    }


def _decimal_from_any(value: Any, field: str) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(MONEY_QUANT)
    if isinstance(value, (int, str)):
        return _to_decimal(value, field)
    _reject_float(value, field)
    _fail(f"invalid_decimal_source:{field}:{type(value).__name__}")


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "value") and not isinstance(value, (str, bytes, bytearray)):
        return str(value.value)
    if hasattr(value, "__dataclass_fields__"):
        return {key: _json_safe(val) for key, val in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _result_to_mapping(result: Any) -> Mapping[str, Any]:
    if isinstance(result, Mapping):
        return result
    if hasattr(result, "__dataclass_fields__"):
        return asdict(result)
    if hasattr(result, "__dict__"):
        return dict(vars(result))
    _fail(f"unsupported_financial_result_type:{type(result).__name__}")


def _iter_financial_mappings(value: Any, *, depth: int = 0) -> Iterable[Mapping[str, Any]]:
    if depth > 4:
        return

    try:
        mapped = _result_to_mapping(value)
    except DropiCatalogEvaluationError:
        return

    if not isinstance(mapped, Mapping):
        return

    yield mapped

    nested_keys = (
        "financial_result",
        "financials",
        "financial",
        "financial_evaluation",
        "evaluation",
        "result",
        "payload",
        "data",
    )

    for key in nested_keys:
        if key in mapped and mapped[key] is not None:
            yield from _iter_financial_mappings(mapped[key], depth=depth + 1)


def _unwrap_financial_result(financial: Mapping[str, Any]) -> Mapping[str, Any]:
    for mapped in _iter_financial_mappings(financial):
        if "scenarios" in mapped:
            return mapped

    available = ",".join(sorted(str(key) for key in financial.keys()))
    _fail(f"financial_result_missing_scenarios:keys={available}")


def _decision_to_str(value: Any) -> str:
    if hasattr(value, "value"):
        raw = str(value.value)
    else:
        raw = str(value)
    return raw.split(".")[-1].upper()


def _extract_base_scenario(financial: Mapping[str, Any]) -> Mapping[str, Any]:
    scenarios = financial.get("scenarios")
    if scenarios is None:
        _fail("financial_result_missing_scenarios")

    if isinstance(scenarios, Mapping):
        for key in ("BASE", "base", "ScenarioName.BASE"):
            if key in scenarios:
                scenario = scenarios[key]
                if hasattr(scenario, "__dataclass_fields__"):
                    return asdict(scenario)
                if isinstance(scenario, Mapping):
                    return scenario
        first = next(iter(scenarios.values()))
        if hasattr(first, "__dataclass_fields__"):
            return asdict(first)
        if isinstance(first, Mapping):
            return first

    if isinstance(scenarios, Sequence) and not isinstance(scenarios, (str, bytes, bytearray)):
        for scenario in scenarios:
            mapped = asdict(scenario) if hasattr(scenario, "__dataclass_fields__") else scenario
            if not isinstance(mapped, Mapping):
                continue
            name = str(mapped.get("name", "")).upper()
            if "BASE" in name:
                return mapped
        if scenarios:
            first = scenarios[0]
            if hasattr(first, "__dataclass_fields__"):
                return asdict(first)
            if isinstance(first, Mapping):
                return first

    _fail("financial_result_base_scenario_not_found")


def _threshold_accepts(
    *,
    contribution_margin: Decimal,
    sale_price: Decimal,
    assumptions: DropiCatalogEvaluationAssumptions,
) -> tuple[bool, str | None, Decimal]:
    if assumptions.min_margin_mxn is not None:
        margin_pct = (contribution_margin / sale_price).quantize(PCT_QUANT)
        if contribution_margin < assumptions.min_margin_mxn:
            return False, "below_min_margin_mxn", margin_pct
        return True, None, margin_pct

    if assumptions.min_margin_pct is None:
        _fail("missing_margin_threshold")

    margin_pct = (contribution_margin / sale_price).quantize(PCT_QUANT)
    if margin_pct < assumptions.min_margin_pct:
        return False, "below_min_margin_pct", margin_pct
    return True, None, margin_pct


def _evaluate_candidate(
    candidate: Mapping[str, Any],
    assumptions: DropiCatalogEvaluationAssumptions,
) -> DropiCatalogEvaluationItem:
    stock_status = "in_stock" if int(candidate["stock"]) > 0 else "out_of_stock"
    min_margin_required = (
        assumptions.min_margin_mxn
        if assumptions.min_margin_mxn is not None
        else (assumptions.sale_price_mxn * assumptions.min_margin_pct).quantize(MONEY_QUANT)
    )

    product = {
        "supplier_product_id": candidate["sku"],
        "product_id": candidate["product_id"],
        "id": candidate["id"],
        "sku": candidate["sku"],
        "name": candidate["name"],
        "title": candidate["title"],
        "landed_cost": candidate["landed_cost"],
        "landed_cost_mxn": candidate["landed_cost_mxn"],
        "cost_mxn": candidate["landed_cost_mxn"],
        "price": assumptions.sale_price_mxn,
        "price_mxn": assumptions.sale_price_mxn,
        "stock": candidate["stock"],
        "category": candidate["category"] or "uncategorized",
        "brand": candidate["brand"],
        "costs": {
            "supplier_cost": str(candidate["supplier_cost_mxn"]),
            "supplier_cost_mxn": candidate["supplier_cost_mxn"],
            "shipping_cost_estimate": str(candidate["shipping_cost_mxn"]),
            "shipping_cost_mxn": candidate["shipping_cost_mxn"],
            "fees_estimate": "0.00",
            "currency": "MXN",
            "min_margin_required": str(min_margin_required),
            "landed_cost_mxn": candidate["landed_cost_mxn"],
            "landed_cost": candidate["landed_cost_mxn"],
            "cost_mxn": candidate["landed_cost_mxn"],
            "total_cost_mxn": candidate["landed_cost_mxn"],
        },
        "inventory": {
            "stock_status": stock_status,
            "stock_quantity": candidate["stock"],
            "stock": candidate["stock"],
            "available_stock": candidate["stock"],
            "available_units": candidate["stock"],
            "quantity": candidate["stock"],
            "quantity_available": candidate["stock"],
            "inventory_count": candidate["stock"],
            "in_stock": candidate["stock"] > 0,
        },
        "safety": {
            "local_only": True,
            "read_only": True,
            "fixture_only": True,
            "dry_run": True,
            "external_side_effects": False,
            "external_writes": False,
            "network": False,
            "network_required": False,
            "live_api": False,
            "live_dropi": False,
            "live_shopify": False,
            "live_meta": False,
            "credentials_required": False,
            "credentials_present": False,
            "orders": False,
            "order_placement": False,
            "fulfillment": False,
            "fulfillment_automation": False,
            "inventory_reservation": False,
            "spend": False,
            "operator_review_required": True,
            "human_review_required": True,
        },
    }

    supplier = {
        "supplier_id": candidate["supplier"],
        "supplier_name": candidate["supplier"],
        "id": candidate["supplier"],
        "name": candidate["supplier"],
        "supplier": candidate["supplier"],
        "stock": candidate["stock"],
        "supplier_rating": candidate["supplier_rating"],
        "rating": candidate["supplier_rating"],
        "shipping_days": candidate["shipping_days"],
        "shipping_cost_mxn": candidate["shipping_cost_mxn"],
        "supplier_cost_mxn": candidate["supplier_cost_mxn"],
        "shipping": {
            "days": candidate["shipping_days"],
            "cost_mxn": candidate["shipping_cost_mxn"],
            "shipping_cost_mxn": candidate["shipping_cost_mxn"],
        },
    }

    financial_raw = evaluate_dropi_candidate_financials(
        product=product,
        supplier=supplier,
        price=assumptions.sale_price_mxn,
        estimated_cac=assumptions.estimated_cac_mxn,
        expected_units=assumptions.expected_units,
    )
    financial_payload = _result_to_mapping(financial_raw)
    financial = _unwrap_financial_result(financial_payload)
    base = _extract_base_scenario(financial)

    contribution_margin = _decimal_from_any(
        base.get("contribution_margin"),
        "financial.scenarios.BASE.contribution_margin",
    )
    landed_cost = _decimal_from_any(
        base.get("landed_cost", candidate["landed_cost_mxn"]),
        "financial.scenarios.BASE.landed_cost",
    )

    threshold_ok, threshold_reject_reason, contribution_margin_pct = _threshold_accepts(
        contribution_margin=contribution_margin,
        sale_price=assumptions.sale_price_mxn,
        assumptions=assumptions,
    )

    financial_decision = _decision_to_str(financial.get("decision", financial_payload.get("decision", "UNKNOWN")))
    financial_reasons_raw = financial.get("reason_codes", financial_payload.get("reason_codes", ()))
    financial_reasons = tuple(str(item) for item in financial_reasons_raw)

    accepted = threshold_ok and financial_decision not in {"KILL", "FAIL"}
    reject_reason = None
    if not threshold_ok:
        reject_reason = threshold_reject_reason
    elif not accepted:
        reject_reason = f"financial_decision_{financial_decision.lower()}"

    return DropiCatalogEvaluationItem(
        sku=str(candidate["sku"]),
        name=str(candidate["name"]),
        supplier=str(candidate["supplier"]),
        source_row_number=int(candidate["source_row_number"]),
        accepted=accepted,
        reject_reason=reject_reason,
        sale_price_mxn=assumptions.sale_price_mxn,
        estimated_cac_mxn=assumptions.estimated_cac_mxn,
        expected_units=assumptions.expected_units,
        landed_cost_mxn=landed_cost,
        contribution_margin_mxn=contribution_margin,
        contribution_margin_pct=contribution_margin_pct,
        financial_decision=financial_decision,
        financial_reason_codes=financial_reasons,
        financial_payload=_json_safe(financial_payload),
    )


def _ranking_key(item: DropiCatalogEvaluationItem) -> tuple[int, Decimal, Decimal, str]:
    return (
        0 if item.accepted else 1,
        -item.contribution_margin_mxn,
        -item.contribution_margin_pct,
        item.sku,
    )


def build_dropi_catalog_evaluated_shortlist(
    records: Iterable[DropiCatalogImportRecord],
    assumptions: DropiCatalogEvaluationAssumptions,
    *,
    max_items: int = 20,
    evidence_path: str | Path | None = None,
    source: str = "records",
) -> DropiCatalogEvaluationResult:
    if not isinstance(assumptions, DropiCatalogEvaluationAssumptions):
        _fail("invalid_assumptions_type")

    if isinstance(max_items, bool) or not isinstance(max_items, int) or max_items <= 0:
        _fail("max_items_must_be_positive_int")

    materialized_records = tuple(records)
    if not materialized_records:
        _fail("no_records_to_evaluate")

    candidates = [_record_to_candidate(record) for record in materialized_records]
    items = tuple(sorted((_evaluate_candidate(candidate, assumptions) for candidate in candidates), key=_ranking_key))
    limited_items = items[:max_items]

    result = DropiCatalogEvaluationResult(
        source=source,
        source_record_count=len(materialized_records),
        accepted_count=sum(1 for item in limited_items if item.accepted),
        rejected_count=sum(1 for item in limited_items if not item.accepted),
        assumptions=assumptions,
        items=limited_items,
    )

    if evidence_path is not None:
        write_dropi_catalog_evaluation_evidence(result, evidence_path)

    return result


def build_dropi_catalog_evaluated_shortlist_from_csv(
    path: str | Path,
    assumptions: DropiCatalogEvaluationAssumptions,
    *,
    max_items: int = 20,
    evidence_path: str | Path | None = None,
) -> DropiCatalogEvaluationResult:
    csv_path = Path(path)
    records = parse_dropi_catalog_csv(csv_path)
    return build_dropi_catalog_evaluated_shortlist(
        records,
        assumptions,
        max_items=max_items,
        evidence_path=evidence_path,
        source=str(csv_path),
    )


def write_dropi_catalog_evaluation_evidence(
    result: DropiCatalogEvaluationResult,
    evidence_path: str | Path,
) -> Path:
    path = Path(evidence_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema": "synapse.a8_r97.dropi_catalog_evaluation.v1",
        "source": result.source,
        "source_record_count": result.source_record_count,
        "accepted_count": result.accepted_count,
        "rejected_count": result.rejected_count,
        "assumptions": _json_safe(result.assumptions),
        "items": [_json_safe(item) for item in result.items],
        "safety": {
            "local_only": True,
            "live_dropi": False,
            "live_shopify": False,
            "live_meta": False,
            "external_writes": False,
            "orders": False,
            "fulfillment": False,
            "spend": False,
        },
    }

    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return path