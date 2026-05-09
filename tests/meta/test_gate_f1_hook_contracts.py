import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "gate_f1.ps1"


EXPECTED_NATIVE_HOOK_LABELS = {
    "staged_files_present",
    "staged_no_utf8_bom",
    "staged_no_crlf",
    "gate_contract_static",
    "static_test_py_compile",
}


def _gate_text() -> str:
    return GATE.read_text(encoding="utf-8")


def _hook_block(text: str) -> str:
    match = re.search(r"(?s)# HOOK:.*?# A8-R37 HOOK FAST PATH END", text)
    assert match is not None
    return match.group(0)


def test_a8_r37_hook_native_fast_path_markers_present() -> None:
    text = _gate_text()
    required = [
        "A8R37_HOOK_STABILIZATION_ACTIVE=1",
        "A8R37_HOOK_EARLIEST_FAST_PATH_ACTIVE=1",
        "A8R37_HOOK_NATIVE_FAST_PATH_ACTIVE=1",
        "A8R37_HOOK_PYTEST_DISABLED=1",
        "A8R37_HOOK_TARGET_BEGIN",
        "A8R37_HOOK_TARGET_RC",
        "A8R37_HOOK_TARGET_END",
        "a8r37_hook_earliest_fast_path=1",
        "a8r37_hook_native_fast_path=1",
        "a8r37_hook_pytest_disabled=1",
        "SKIPPED_HOOK_FAST_PATH",
        "# A8-R37 HOOK FAST PATH END",
    ]
    missing = [token for token in required if token not in text]
    assert missing == []


def test_a8_r37_hook_fast_path_runs_immediately_after_venv_before_prechecks() -> None:
    text = _gate_text()
    venv_index = text.index("PYTHON_VENV_DETECTED=")
    hook_index = text.index("# A8-R37: earliest hook fast path runs immediately after venv detection")
    doctor_index = text.index("# DOCTOR")
    doctor_command_index = text.index("synapse.infra.doctor")
    no_bom_index = text.find("NO_BOM_OK")
    assert venv_index < hook_index
    assert hook_index < doctor_index
    assert hook_index < doctor_command_index
    if no_bom_index != -1:
        assert hook_index < no_bom_index


def test_a8_r37_hook_uses_native_checks_not_pytest() -> None:
    hook = _hook_block(_gate_text())
    assert "Invoke-A8R37HookCheck" in hook
    assert "Invoke-A8R28CheckedPytest" not in hook
    assert "gate_pytest_hook_targets" not in hook
    assert "-m pytest" not in hook
    assert "--assert=plain" not in hook
    assert "> $stdout" not in hook
    assert "2> $stderr" not in hook


def test_a8_r37_native_hook_labels_are_explicit_and_complete() -> None:
    hook = _hook_block(_gate_text())
    labels = set(re.findall(r'Invoke-A8R37HookCheck -Label "([^"]+)"', hook))
    assert labels == EXPECTED_NATIVE_HOOK_LABELS


def test_a8_r37_hook_contract_has_no_interactive_prompts() -> None:
    text = _gate_text()
    assert "Read-Host" not in text
    assert "Start-Sleep" not in text
    assert re.search(r"(^|[^A-Za-z])pause([^A-Za-z]|$)", text, flags=re.IGNORECASE) is None

def test_a8_r39_hook_fast_path_guards_product_candidate_contract_surface() -> None:
    """The native hook must protect the A8-R38 product candidate meta-contract."""

    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    gate_text = (root / "scripts/gate_f1.ps1").read_text(encoding="utf-8")
    contract_text = (
        root / "tests/meta/test_a8_r38_product_candidate_contract_surface.py"
    ).read_text(encoding="utf-8")

    assert "a8_r38_product_candidate_contract_surface" in gate_text
    assert "tests/meta/test_a8_r38_product_candidate_contract_surface.py" in gate_text
    assert "A8_R39_META_CONTRACT_TEST_MISSING" in gate_text
    assert "A8_R39_META_CONTRACT_IMPORTS_RUNTIME" in gate_text
    assert "-m pytest" not in gate_text
    assert "Invoke-A8R28CheckedPytest" not in gate_text

    assert contract_text.count("\ndef test_") == 4
    assert "def _combined_contract_surface()" in contract_text
    assert "SURFACE_TERMS" in contract_text
    assert "CONTRACT_MARKERS" in contract_text
    assert "They do not change product-selection behavior." in contract_text
    assert "from synapse." not in contract_text
    assert "import synapse" not in contract_text

def test_a8_r39_hook_target_report_count_matches_native_labels() -> None:
    """The hook target report must match the native hook label surface."""

    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    gate_text = (root / "scripts/gate_f1.ps1").read_text(encoding="utf-8")

    hook_match = re.search(
        r"(?s)# HOOK:.*?# A8-R37 HOOK FAST PATH END",
        gate_text,
    )
    assert hook_match is not None

    hook_block = hook_match.group(0)
    labels = re.findall(r'Invoke-A8R37HookCheck\s+-Label\s+"([^"]+)"', hook_block)
    report_match = re.search(r"HOOK_TEST_TARGETS_FOUND=(\d+)", gate_text)

    assert report_match is not None
    assert len(labels) == 6
    assert len(set(labels)) == 6
    assert "a8_r38_product_candidate_contract_surface" in labels
    assert int(report_match.group(1)) == len(labels)
    assert "HOOK_TEST_TARGETS_FOUND=5" not in gate_text
    assert "HOOK_TEST_TARGETS_FOUND=6" in gate_text
    assert "-m pytest" not in hook_block
    assert "Invoke-A8R28CheckedPytest" not in hook_block
