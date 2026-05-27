from __future__ import annotations# Auto-load .env.local when running from repo root.
# SYNAPSE A8-R57 PYTEST STARTUP GUARD START
def _synapse_a8_r57_seed_windows_platform_cache():
    """Avoid subprocess-backed platform.win32_ver during pytest import startup on Windows."""
    try:
        import sys as _synapse_sys
        if _synapse_sys.platform != "win32":
            return

        import platform as _synapse_platform
        if getattr(_synapse_platform, "_uname_cache", None) is not None:
            return

        _version_info = _synapse_sys.getwindowsversion()
        _release = str(_version_info.major)
        _version = f"{_version_info.major}.{_version_info.minor}.{_version_info.build}"

        _synapse_platform._uname_cache = _synapse_platform.uname_result(
            "Windows",
            "",
            _release,
            _version,
            "",
            "",
        )
    except Exception:
        return


def _synapse_a8_r57_disable_external_pytest_plugin_autoload():
    """Disable external pytest11 plugin autoload for deterministic local pytest startup."""
    try:
        import os as _synapse_os
        _synapse_os.environ.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    except Exception:
        return


_synapse_a8_r57_disable_external_pytest_plugin_autoload()
_synapse_a8_r57_seed_windows_platform_cache()
# SYNAPSE A8-R57 PYTEST STARTUP GUARD END
# Safe: no imprime secretos, no truena si falta el archivo.

try:
    from synapse.infra.envfile import load_env_file
    load_env_file(".env.local", override=False)
except Exception:
    pass
