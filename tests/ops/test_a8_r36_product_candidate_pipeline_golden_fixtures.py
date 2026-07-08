from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_CLI = REPO_ROOT / "tools" / "product_candidate_pipeline_cli.py"

FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "product_candidate_sources"
GOLDEN_DIR = REPO_ROOT / "tests" / "golden" / "product_candidate_pipeline"

EXPECTED_OUTPUT_FILES = {
    "normalized_candidate_source.json",
    "product_decision_artifact.json",
    "product_candidate_pipeline_manifest.json",
}

NETWORK_MARKERS = (
    "http://",
    "https://",
    "www.",
    "requests.",
    "aiohttp",
    "urllib",
    "shopify_admin",
    "facebook_graph",
    "meta_ads",
    "scrape",
)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def walk(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []

    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            rows.append((path, child))
            rows.extend(walk(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            path = f"{prefix}[{index}]"
            rows.append((path, child))
            rows.extend(walk(child, path))

    return rows


def first_key(value: Any, key: str) -> Any:
    for path, child in walk(value):
        if path.split(".")[-1] == key:
            return child
    raise AssertionError(f"missing key: {key}")


def hash_paths(value: Any) -> list[str]:
    paths: list[str] = []

    for path, child in walk(value):
        lower = path.lower()
        if ("hash" not in lower) and ("sha256" not in lower):
            continue
        if isinstance(child, str) and len(child.strip()) >= 12:
            paths.append(path)

    return paths


def network_hits(*values: Any) -> list[str]:
    text = json_text(values).lower()
    return sorted({marker for marker in NETWORK_MARKERS if marker in text})


def run_pipeline(fixture_name: str, output_dir: Path, expect_success: bool) -> subprocess.CompletedProcess[str]:
    output_dir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [
            sys.executable,
            str(PIPELINE_CLI),
            "--input",
            str(FIXTURE_DIR / fixture_name),
            "--output-dir",
            str(output_dir),
            "--pretty",
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
    )

    if expect_success:
        assert result.returncode == 0, {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }

        actual_files = {path.name for path in output_dir.iterdir() if path.is_file()}
        assert actual_files == EXPECTED_OUTPUT_FILES, {
            "expected": sorted(EXPECTED_OUTPUT_FILES),
            "actual": sorted(actual_files),
        }
    else:
        assert result.returncode != 0, "empty fixture must fail with non-zero RC"
        assert "traceback" not in (result.stdout + result.stderr).lower(), {
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    return result


def test_a8_r36_valid_fixture_matches_golden_contract(tmp_path: Path) -> None:
    manifest_golden = load_json(GOLDEN_DIR / "expected_manifest_valid_winning_batch.json")
    source_golden = load_json(GOLDEN_DIR / "expected_source_valid_winning_batch.json")
    decision_golden = load_json(GOLDEN_DIR / "expected_decision_valid_winning_batch.json")

    out_dir = tmp_path / "valid"
    run_pipeline("a8_r36_valid_winning_batch.json", out_dir, expect_success=True)

    manifest = load_json(out_dir / "product_candidate_pipeline_manifest.json")
    source = load_json(out_dir / "normalized_candidate_source.json")
    decision = load_json(out_dir / "product_decision_artifact.json")

    assert first_key(manifest, "champion_sku") == manifest_golden["expected_champion_sku"]
    assert decision_golden["expected_champion_sku"] in json_text(decision)

    assert first_key(manifest, "manual_selection_used") is False
    assert first_key(manifest, "manual_champion_provided") is False
    assert first_key(manifest, "local_only_execution") is True

    source_candidates = source["candidates"]
    assert len(source_candidates) == source_golden["expected_candidate_count"]
    assert len(source["rejected_rows"]) == source_golden["expected_rejected_rows"]
    assert source["quality_gates"]["ready_for_product_decision_cli"] is True

    source_text = json_text(source)
    for sku in source_golden["expected_skus"]:
        assert sku in source_text

    observed_hash_paths = hash_paths(manifest)
    assert len(observed_hash_paths) >= manifest_golden["minimum_required_hash_fields"], observed_hash_paths
    assert network_hits(manifest, source, decision) == []


def test_a8_r36_mixed_fixture_preserves_valid_candidates_and_rejects_bad_rows(tmp_path: Path) -> None:
    out_dir = tmp_path / "mixed"
    run_pipeline("a8_r36_mixed_quality_batch.json", out_dir, expect_success=True)

    manifest = load_json(out_dir / "product_candidate_pipeline_manifest.json")
    source = load_json(out_dir / "normalized_candidate_source.json")
    decision = load_json(out_dir / "product_decision_artifact.json")

    assert first_key(manifest, "champion_sku") == "A8R36-MIXED-CHAMPION-001"

    assert len(source["candidates"]) == 2
    assert len(source["rejected_rows"]) == 2
    assert source["quality_gates"]["ready_for_product_decision_cli"] is True

    combined = json_text({"manifest": manifest, "source": source, "decision": decision})
    assert "A8R36-MIXED-CHAMPION-001" in combined
    assert "A8R36-MIXED-VALID-002" in combined
    assert network_hits(manifest, source, decision) == []


def test_a8_r36_empty_fixture_fails_without_traceback(tmp_path: Path) -> None:
    out_dir = tmp_path / "empty"
    result = run_pipeline("a8_r36_invalid_empty_batch.json", out_dir, expect_success=False)

    combined_output = (result.stdout + result.stderr).lower()
    assert any(
        token in combined_output
        for token in (
            "source rows must not be empty",
            "candidates must not be empty",
            "empty",
            "candidate",
        )
    ), {
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
