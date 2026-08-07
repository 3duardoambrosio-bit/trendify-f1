from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


def _assert_learning_output(
    output: str,
    *,
    status: str,
    dry_run: bool,
    apply_requested: bool,
    writes_allowed: bool,
    rc: int,
) -> None:
    assert f"LEARNING_STATUS={status}" in output
    assert f"LEARNING_DRY_RUN={str(dry_run).lower()}" in output
    assert f"LEARNING_APPLY_REQUESTED={str(apply_requested).lower()}" in output
    assert f"LEARNING_WRITES_ALLOWED={str(writes_allowed).lower()}" in output
    assert f"LEARNING_RC={rc}" in output


def test_cli_learning_dry_run_no_heavy_imports(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    import synapse.cli.commands.learning_cmd as learning_cmd  # noqa: WPS433
    from synapse.cli.main import main  # noqa: WPS433
    import sys as _sys  # noqa: WPS433

    def bomb(*args, **kwargs):
        raise AssertionError("default learning mode must not invoke the engine")

    monkeypatch.setattr(learning_cmd, "invoke_module", bomb)
    monkeypatch.delitem(_sys.modules, "synapse.learning.learning_loop", raising=False)
    monkeypatch.chdir(tmp_path)

    rc = main(["learning"])

    assert rc == 0
    assert "synapse.learning.learning_loop" not in _sys.modules
    assert list(tmp_path.rglob("*")) == []
    _assert_learning_output(
        capsys.readouterr().out,
        status="DEFAULT_NOOP",
        dry_run=True,
        apply_requested=False,
        writes_allowed=False,
        rc=0,
    )


def test_cli_learning_explicit_dry_run_ok(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    import synapse.cli.commands.learning_cmd as learning_cmd  # noqa: WPS433
    from synapse.cli.main import main  # noqa: WPS433

    def bomb(*args, **kwargs):
        raise AssertionError("CLI dry-run must not invoke the engine")

    monkeypatch.setattr(learning_cmd, "invoke_module", bomb)
    monkeypatch.chdir(tmp_path)

    rc = main(["learning", "--dry-run"])

    assert rc == 0
    assert list(tmp_path.rglob("*")) == []
    _assert_learning_output(
        capsys.readouterr().out,
        status="DRY_RUN_NOOP",
        dry_run=True,
        apply_requested=False,
        writes_allowed=False,
        rc=0,
    )


def test_cli_learning_apply_invokes_learning_module(monkeypatch) -> None:
    import synapse.cli.commands.learning_cmd as learning_cmd  # noqa: WPS433
    from synapse.cli.main import main  # noqa: WPS433

    calls: list[dict[str, object]] = []

    def fake_invoke_module(modname: str, argv: list[str] | None = None, **kwargs: object) -> int:
        calls.append(
            {
                "modname": modname,
                "argv": argv,
                "kwargs": kwargs,
            }
        )
        return 0

    monkeypatch.setattr(learning_cmd, "invoke_module", fake_invoke_module)
    monkeypatch.delenv("SYNAPSE_READONLY", raising=False)

    rc = main(["learning", "--apply"])

    assert rc == 0
    assert calls == [
        {
            "modname": "synapse.learning.learning_loop",
            "argv": ["--apply"],
            "kwargs": {},
        }
    ]


def test_cli_learning_apply_propagates_nonzero_rc(monkeypatch) -> None:
    import synapse.cli.commands.learning_cmd as learning_cmd  # noqa: WPS433
    from synapse.cli.main import main  # noqa: WPS433

    def fake_invoke_module(modname: str, argv: list[str] | None = None, **kwargs: object) -> int:
        assert modname == "synapse.learning.learning_loop"
        assert argv == ["--apply"]
        assert kwargs == {}
        return 2

    monkeypatch.setattr(learning_cmd, "invoke_module", fake_invoke_module)
    monkeypatch.delenv("SYNAPSE_READONLY", raising=False)

    rc = main(["learning", "--apply"])

    assert rc == 2


def test_cli_learning_apply_readonly_blocks_before_dispatch_or_paths(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    import synapse.cli.commands.learning_cmd as learning_cmd  # noqa: WPS433
    from synapse.cli.main import main  # noqa: WPS433

    def bomb(*args, **kwargs):
        raise AssertionError("read-only apply must not dispatch")

    monkeypatch.setattr(learning_cmd, "invoke_module", bomb)
    monkeypatch.setenv("SYNAPSE_READONLY", "1")
    monkeypatch.chdir(tmp_path)

    rc = main(["learning", "--apply"])

    assert rc == 2
    assert list(tmp_path.rglob("*")) == []
    _assert_learning_output(
        capsys.readouterr().out,
        status="READONLY_BLOCKED",
        dry_run=False,
        apply_requested=True,
        writes_allowed=False,
        rc=2,
    )


def test_cli_learning_apply_crash_reports_and_returns_3(monkeypatch) -> None:
    import synapse.cli.commands.learning_cmd as learning_cmd  # noqa: WPS433
    import synapse.cli.main as cli_main  # noqa: WPS433

    seen: dict[str, object] = {}
    printed: list[str] = []

    def boom(modname: str, argv: list[str] | None = None, **kwargs: object) -> int:
        assert modname == "synapse.learning.learning_loop"
        assert argv == ["--apply"]
        assert kwargs == {}
        raise RuntimeError("boom")

    def fake_capture_exception(exc: Exception, context: dict[str, object]) -> SimpleNamespace:
        seen["exc"] = exc
        seen["context"] = context
        return SimpleNamespace(
            path=r"C:\Temp\synapse_cli_learning_crash.json",
            fingerprint="fp-learning-001",
        )

    def fake_suggest_fix(exc: Exception) -> str:
        assert isinstance(exc, RuntimeError)
        return "check learning command failure path"

    def fake_cli_print(message: str, flush: bool = True) -> None:
        assert flush is True
        printed.append(message)

    monkeypatch.setattr(learning_cmd, "invoke_module", boom)
    monkeypatch.delenv("SYNAPSE_READONLY", raising=False)
    monkeypatch.setattr(cli_main, "capture_exception", fake_capture_exception)
    monkeypatch.setattr(cli_main, "suggest_fix", fake_suggest_fix)
    monkeypatch.setattr(cli_main, "cli_print", fake_cli_print)

    rc = cli_main.main(["learning", "--apply"])

    assert rc == 3
    assert isinstance(seen["exc"], RuntimeError)

    context = seen["context"]
    assert isinstance(context, dict)
    assert "cli" in context

    cli_context = context["cli"]
    assert isinstance(cli_context, dict)
    assert cli_context["command"] == "learning"
    assert cli_context["argv"] == ["learning", "--apply"]

    assert any("RuntimeError: boom" in line for line in printed)
    assert any("HINT" in line and "check learning command failure path" in line for line in printed)
    assert any("crash_report=C:\\Temp\\synapse_cli_learning_crash.json" in line for line in printed)
    assert any("fingerprint=fp-learning-001" in line for line in printed)
    assert any("python -m synapse.cli triage --path" in line for line in printed)
