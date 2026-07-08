from __future__ import annotations

from types import SimpleNamespace


def test_cli_learning_dry_run_no_heavy_imports() -> None:
    from synapse.cli.main import main  # noqa: WPS433
    import sys as _sys  # noqa: WPS433

    rc = main(["learning"])
    assert rc == 0
    assert "synapse.learning.learning_loop" not in _sys.modules


def test_cli_learning_explicit_dry_run_ok() -> None:
    from synapse.cli.main import main  # noqa: WPS433

    rc = main(["learning", "--dry-run"])
    assert rc == 0


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

    rc = main(["learning", "--apply"])

    assert rc == 0
    assert calls == [
        {
            "modname": "synapse.learning.learning_loop",
            "argv": [],
            "kwargs": {},
        }
    ]


def test_cli_learning_apply_propagates_nonzero_rc(monkeypatch) -> None:
    import synapse.cli.commands.learning_cmd as learning_cmd  # noqa: WPS433
    from synapse.cli.main import main  # noqa: WPS433

    def fake_invoke_module(modname: str, argv: list[str] | None = None, **kwargs: object) -> int:
        assert modname == "synapse.learning.learning_loop"
        assert argv == []
        assert kwargs == {}
        return 7

    monkeypatch.setattr(learning_cmd, "invoke_module", fake_invoke_module)

    rc = main(["learning", "--apply"])

    assert rc == 7


def test_cli_learning_apply_crash_reports_and_returns_3(monkeypatch) -> None:
    import synapse.cli.commands.learning_cmd as learning_cmd  # noqa: WPS433
    import synapse.cli.main as cli_main  # noqa: WPS433

    seen: dict[str, object] = {}
    printed: list[str] = []

    def boom(modname: str, argv: list[str] | None = None, **kwargs: object) -> int:
        assert modname == "synapse.learning.learning_loop"
        assert argv == []
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