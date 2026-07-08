from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from synapse.cli import simulate

MOJIBAKE_MARKERS = ("\u00c3", "\u00c2", "\ufffd")


def _iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _iter_strings(key)
            yield from _iter_strings(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_strings(item)


def _marker_hits(value: Any) -> list[str]:
    hits: list[str] = []
    for text in _iter_strings(value):
        if any(marker in text for marker in MOJIBAKE_MARKERS):
            hits.append(text)
    return hits


def test_a8_r62_simulate_source_has_no_mojibake_literals() -> None:
    source = Path(simulate.__file__).read_text(encoding="utf-8")

    assert sum(source.count(marker) for marker in MOJIBAKE_MARKERS) == 0
    assert "\u00e1ngulo" in source
    assert "fricci\u00f3n" in source
    assert "ense\u00f1a" in source
    assert "demostraci\u00f3n" in source


def test_a8_r62_known_case_inputs_have_no_mojibake() -> None:
    cases = simulate._known_case_inputs()

    hits = _marker_hits(cases)

    assert hits == []


def test_a8_r62_generated_creative_pack_has_no_mojibake() -> None:
    scenario = simulate.build_scenario(None)
    safety = simulate.build_safety_posture(
        f"{scenario.creative_claim} {scenario.primary_hook} {scenario.marketing_angle}"
    )

    creative_pack = simulate.generate_creative_pack(scenario, safety)

    hits = _marker_hits(creative_pack)

    assert hits == []


def test_a8_r62_written_evidence_has_no_mojibake(tmp_path: Path) -> None:
    scenario = simulate.build_scenario(None)
    safety = simulate.build_safety_posture(
        f"{scenario.creative_claim} {scenario.primary_hook} {scenario.marketing_angle}"
    )
    score = simulate.evaluate_score(scenario.signals)
    decision = simulate.make_decision(scenario, score, safety)
    creative_pack = simulate.generate_creative_pack(scenario, safety)

    evidence_dir = simulate.create_evidence_dir(str(tmp_path))
    simulate.write_evidence(evidence_dir, scenario, safety, decision, creative_pack)

    generated_files = sorted(
        path for path in evidence_dir.iterdir()
        if path.suffix in {".json", ".ndjson", ".txt"}
    )

    assert generated_files

    for path in generated_files:
        raw = path.read_text(encoding="utf-8")
        assert sum(raw.count(marker) for marker in MOJIBAKE_MARKERS) == 0, path

        if path.suffix == ".json":
            hits = _marker_hits(json.loads(raw))
            assert hits == [], path
