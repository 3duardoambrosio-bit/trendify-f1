import os
import platform
import sys

import pytest


def test_windows_platform_cache_guard_seeded_before_hypothesis_imports() -> None:
    if sys.platform != "win32":
        pytest.skip("Windows-only import-time guard")

    cache = getattr(platform, "_uname_cache", None)

    assert cache is not None
    assert cache.system == "Windows"
    assert platform.system() == "Windows"


def test_pytest_external_plugin_autoload_disabled_for_deterministic_startup() -> None:
    assert os.environ.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") == "1"
