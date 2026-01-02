from __future__ import annotations

from pathlib import Path

from synapse.infra.diagnostics import (
    capture_exception,
    exception_fingerprint,
    find_latest_report,
    load_report,
    suggest_fix,
)


def test_exception_fingerprint_stable() -> None:
    try:
        raise ValueError("boom")
    except ValueError as e:
        fp1 = exception_fingerprint(e)
        fp2 = exception_fingerprint(e)
        assert fp1 == fp2


def test_capture_exception_writes_json_no_bom(tmp_path: Path) -> None:
    try:
        1 / 0
    except ZeroDivisionError as e:
        rep = capture_exception(e, context={"k": "v"}, diag_dir=tmp_path)
        raw = rep.path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        payload = load_report(rep.path)
        assert payload["fingerprint"] == rep.fingerprint
        assert payload["frames"], "expected structured frames"
        assert "traceback" in payload


def test_find_latest_report(tmp_path: Path) -> None:
    try:
        raise RuntimeError("a")
    except RuntimeError as e:
        capture_exception(e, diag_dir=tmp_path)
    latest = find_latest_report(tmp_path)
    assert latest is not None
    assert latest.exists()


def test_suggest_fix_message_pattern() -> None:
    e = RuntimeError("canonical_csv not found (tried data/catalog/*.csv candidates)")
    hint = suggest_fix(e)
    assert hint is not None
    assert "canonical" in hint.lower()
