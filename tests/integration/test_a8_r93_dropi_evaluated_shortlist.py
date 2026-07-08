import ast
import importlib.util
import json
import sys
import types
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO / "tests" / "fixtures" / "dropi_supplier_products_nominal.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def modules():
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))

    synapse_pkg = sys.modules.get("synapse")
    if synapse_pkg is None:
        synapse_pkg = types.ModuleType("synapse")
        synapse_pkg.__path__ = [str(REPO / "synapse")]
        sys.modules["synapse"] = synapse_pkg
    elif not hasattr(synapse_pkg, "__path__"):
        synapse_pkg.__path__ = [str(REPO / "synapse")]

    integration_pkg = types.ModuleType("synapse.integration")
    integration_pkg.__path__ = [str(REPO / "synapse" / "integration")]
    sys.modules["synapse.integration"] = integration_pkg
    setattr(synapse_pkg, "integration", integration_pkg)

    fixture_module = _load_module(
        "synapse.integration.dropi_fixture_readonly",
        REPO / "synapse" / "integration" / "dropi_fixture_readonly.py",
    )
    bridge_module = _load_module(
        "synapse.integration.dropi_to_financial_evaluation",
        REPO / "synapse" / "integration" / "dropi_to_financial_evaluation.py",
    )
    shortlist_module = _load_module(
        "synapse.integration.dropi_evaluated_shortlist",
        REPO / "synapse" / "integration" / "dropi_evaluated_shortlist.py",
    )
    return fixture_module, bridge_module, shortlist_module


@pytest.fixture()
def payload(modules):
    fixture_module, _, _ = modules
    return fixture_module.load_dropi_fixture(FIXTURE_PATH)


def test_shortlist_from_fixture_is_operator_ready_and_serializable(modules):
    _, _, shortlist = modules

    result = shortlist.build_dropi_evaluated_shortlist_from_fixture(
        FIXTURE_PATH,
        price=Decimal("399.00"),
        estimated_cac=Decimal("75.00"),
        expected_units=1,
        max_items=3,
    )

    assert result["source"]["type"] == "dropi_fixture"
    assert result["target"]["type"] == "dropi_evaluated_product_shortlist"
    assert result["operator_review_required"] is True
    assert result["boundaries"]["read_only"] is True
    assert result["boundaries"]["live_dropi"] is False
    assert result["boundaries"]["external_writes"] is False
    assert result["boundaries"]["spend"] is False
    assert result["assumptions"] == {
        "price": "399.00",
        "estimated_cac": "75.00",
        "expected_units": 1,
        "max_items": 3,
        "min_contribution_profit": "0.00",
    }
    assert 1 <= len(result["shortlist"]) <= 3
    assert result["summary"]["operator_review_required"] is True

    json.dumps(result, sort_keys=True)


def test_shortlist_ranks_deterministically(modules, payload):
    _, _, shortlist = modules

    first = shortlist.build_dropi_evaluated_shortlist(
        payload,
        price=Decimal("399.00"),
        estimated_cac=Decimal("75.00"),
        max_items=10,
    )
    second = shortlist.build_dropi_evaluated_shortlist(
        payload,
        price=Decimal("399.00"),
        estimated_cac=Decimal("75.00"),
        max_items=10,
    )

    assert first == second

    ranks = [item["rank"] for item in first["shortlist"]]
    assert ranks == list(range(1, len(ranks) + 1))

    profits = [Decimal(item["score"]["contribution_profit"]) for item in first["shortlist"]]
    assert profits == sorted(profits, reverse=True)


def test_shortlist_normalizes_financial_objects_to_dicts(modules, payload):
    _, _, shortlist = modules

    result = shortlist.build_dropi_evaluated_shortlist(
        payload,
        price=Decimal("399.00"),
        estimated_cac=Decimal("75.00"),
        max_items=2,
    )

    assert result["shortlist"]
    item = result["shortlist"][0]
    assert isinstance(item["financial_input"], dict)
    assert isinstance(item["financial_result"], dict)
    assert isinstance(item["candidate"], dict)
    assert isinstance(item["bridge_boundaries"], dict)
    assert all(not hasattr(value, "__dataclass_fields__") for value in item.values())


def test_shortlist_score_uses_price_landed_cost_and_cac(modules, payload):
    _, _, shortlist = modules

    result = shortlist.build_dropi_evaluated_shortlist(
        payload,
        price=Decimal("399.00"),
        estimated_cac=Decimal("75.00"),
        max_items=1,
    )

    item = result["shortlist"][0]
    score = item["score"]
    expected = Decimal(score["price"]) - Decimal(score["landed_cost"]) - Decimal(score["estimated_cac"])
    assert Decimal(score["contribution_profit"]) == expected


def test_shortlist_fail_closes_bridge_rejections(modules, payload):
    _, bridge, shortlist = modules
    calls = {"count": 0}

    def evaluator(*, product, supplier, price, estimated_cac, expected_units):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("synthetic unsafe candidate")
        return bridge.evaluate_dropi_candidate_financials(
            product=product,
            supplier=supplier,
            price=price,
            estimated_cac=estimated_cac,
            expected_units=expected_units,
        )

    result = shortlist.build_dropi_evaluated_shortlist(
        payload,
        price=Decimal("399.00"),
        estimated_cac=Decimal("75.00"),
        evaluator=evaluator,
        max_items=10,
    )

    assert result["rejections"]
    rejection = result["rejections"][0]
    assert rejection["status"] == "rejected_fail_closed"
    assert rejection["code"] == "BRIDGE_FAIL_CLOSED"
    assert "synthetic unsafe candidate" in rejection["reason"]
    assert rejection["product"]["index"] == 0
    assert rejection["operator_review_required"] is True
    assert rejection["boundaries"]["read_only"] is True


def test_shortlist_rejects_below_min_contribution_profit(modules, payload):
    _, _, shortlist = modules

    result = shortlist.build_dropi_evaluated_shortlist(
        payload,
        price=Decimal("399.00"),
        estimated_cac=Decimal("75.00"),
        min_contribution_profit=Decimal("99999.00"),
        max_items=10,
    )

    assert result["shortlist"] == []
    assert result["rejections"]
    assert {item["code"] for item in result["rejections"]} == {"BELOW_MIN_CONTRIBUTION_PROFIT"}


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"price": Decimal("0.00"), "estimated_cac": Decimal("75.00")}, "price"),
        ({"price": Decimal("399.00"), "estimated_cac": Decimal("-1.00")}, "estimated_cac"),
        ({"price": Decimal("399.00"), "estimated_cac": Decimal("75.00"), "expected_units": True}, "expected_units"),
        ({"price": Decimal("399.00"), "estimated_cac": Decimal("75.00"), "max_items": 0}, "max_items"),
    ],
)
def test_shortlist_validates_operator_assumptions(modules, payload, kwargs, fragment):
    _, _, shortlist = modules

    with pytest.raises(shortlist.DropiShortlistError, match=fragment):
        shortlist.build_dropi_evaluated_shortlist(payload, **kwargs)


def test_shortlist_validates_payload_contract(modules):
    _, _, shortlist = modules

    with pytest.raises(shortlist.DropiShortlistError, match="payload"):
        shortlist.build_dropi_evaluated_shortlist(
            [],
            price=Decimal("399.00"),
            estimated_cac=Decimal("75.00"),
        )


def test_shortlist_module_uses_existing_r92_bridge():
    path = REPO / "synapse" / "integration" / "dropi_evaluated_shortlist.py"
    text = path.read_text(encoding="utf-8")

    assert "evaluate_dropi_candidate_financials" in text
    assert "load_dropi_fixture" in text
    assert "build_supplier_surface" in text


def test_shortlist_static_ast_has_no_side_effect_surfaces():
    path = REPO / "synapse" / "integration" / "dropi_evaluated_shortlist.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    forbidden_import_roots = {
        "requests",
        "urllib",
        "httpx",
        "socket",
        "subprocess",
        "os",
        "ftplib",
        "smtplib",
    }
    forbidden_calls = {
        "open",
        "exec",
        "eval",
        "__import__",
        "compile",
    }

    imports = []
    calls = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)

    assert sorted(set(imports) & forbidden_import_roots) == []
    assert sorted(set(calls) & forbidden_calls) == []