from __future__ import annotations

import argparse
import types

from synapse.cli.commands._invoke import invoke_best


def test_invoke_prefers_run_when_kwargs_present() -> None:
    mod = types.ModuleType("m")

    called = {"run": 0, "main": 0}

    def run(*, product_id: str, dry_run: bool = True) -> int:
        called["run"] += 1
        assert product_id == "p1"
        assert dry_run is False
        return 0

    def main(argv=None) -> int:
        called["main"] += 1
        p = argparse.ArgumentParser()
        p.add_argument("--product-id", required=True)
        p.parse_args(argv)
        return 0

    mod.run = run  # type: ignore[attr-defined]
    mod.main = main  # type: ignore[attr-defined]

    rc = invoke_best(mod, argv=[], product_id="p1", dry_run=False)
    assert rc == 0
    assert called["run"] == 1
    assert called["main"] == 0


def test_invoke_can_use_execute_name() -> None:
    mod = types.ModuleType("m3")
    called = {"execute": 0}

    def execute(*, product_id: str) -> int:
        called["execute"] += 1
        assert product_id == "p1"
        return 0

    mod.execute = execute  # type: ignore[attr-defined]
    rc = invoke_best(mod, argv=[], product_id="p1")
    assert rc == 0
    assert called["execute"] == 1


def test_invoke_falls_back_to_main_when_no_kwargs() -> None:
    mod = types.ModuleType("m2")
    called = {"main": 0}

    def main(argv=None) -> int:
        called["main"] += 1
        p = argparse.ArgumentParser()
        p.add_argument("--product-id", required=True)
        ns = p.parse_args(argv)
        assert ns.product_id == "p1"
        return 0

    mod.main = main  # type: ignore[attr-defined]

    rc = invoke_best(mod, argv=["--product-id", "p1"])
    assert rc == 0
    assert called["main"] == 1
