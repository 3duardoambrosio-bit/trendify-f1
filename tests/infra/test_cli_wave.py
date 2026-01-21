from __future__ import annotations


def test_cli_wave_dry_run_ok_no_heavy_imports() -> None:
    from synapse.cli.main import main  # noqa: WPS433
    import sys as _sys  # noqa: WPS433

    rc = main(["wave"])
    assert rc == 0
    assert "synapse.marketing_os.wave_kit_runner" not in _sys.modules
    assert "synapse.marketing_os.wave_runner" not in _sys.modules


def test_cli_wave_apply_requires_product_id() -> None:
    from synapse.cli.main import main  # noqa: WPS433

    rc = main(["wave", "--apply"])
    assert rc == 2


def test_cli_wave_apply_forwards_kwargs(monkeypatch) -> None:
    import synapse.cli.commands.wave_cmd as wc  # noqa: WPS433

    calls = []

    def fake_invoke(modname: str, argv=None, **kwargs):
        calls.append((modname, kwargs))
        return 0

    monkeypatch.setattr(wc, "invoke_module", fake_invoke)

    ns = type(
        "Args",
        (),
        {"product_id": "p1", "apply": True, "dry_run": False, "out_root": r"X:\out", "canonical_csv": r"X:\c.csv"},
    )()
    rc = wc._run(ns)  # type: ignore[arg-type]
    assert rc == 0
    assert calls[0][0] == "synapse.marketing_os.wave_kit_runner"
    assert calls[0][1]["product_id"] == "p1"
    assert calls[0][1]["dry_run"] is False
    assert calls[0][1]["out_root"] == r"X:\out"
    assert calls[0][1]["canonical_csv"] == r"X:\c.csv"
