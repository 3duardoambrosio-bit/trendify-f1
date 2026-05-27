# A8-R57 Close Manifest

A8_R57_CLOSED=1
ISLAND=A8-R57_LOCAL_PYTEST_RUNTIME_STABILITY
BRANCH=feat/ui-read-model
BASE_HEAD=2005fbc94b4b2d7af24a2d4edc5c8833d2d54b7b
ROLLBACK=0

## Root causes

- ROOT_CAUSE_PRIMARY=PYTEST_ENTRYPOINT_NOT_VENV_PINNED
- ROOT_CAUSE_SECONDARY=HYPOTHESIS_IMPORT_TRIGGERS_WINDOWS_PLATFORM_SUBPROCESS
- ROOT_CAUSE_TERTIARY=PYTEST_EXTERNAL_PLUGIN_AUTOLOAD_IMPORTS_ANYIO_SSL
- ROOT_CAUSE_RUNTIME=LOCAL_TERMINAL_INTERRUPTED_PYTHON_STARTUP_DURING_EARLIER_INTERACTIVE_RUNS

## Repair

- sitecustomize.py seeds Windows platform._uname_cache using sys.getwindowsversion().
- sitecustomize.py sets PYTEST_DISABLE_PLUGIN_AUTOLOAD=1.
- Local ignored venv shims route pytest through env/Scripts/python.exe -m pytest.
- External pytest11 plugin autoload is disabled for deterministic local pytest startup.
- No protected product files were intentionally modified.

## Verified gates

- py_compile_sitecustomize=PASS
- py_compile_windows_platform_guard_test=PASS
- python_env_probe_pytest_autoload=PASS
- pytest_version=PASS
- pytest_windows_platform_cache_guard=PASS
- pytest_tests_ui=PASS
- pytest_blacklist_contract=PASS
- pytest_read_model_blacklist_sync=PASS

## Protected files

- synapse/cli/_blacklist.py: unchanged required
- synapse/cli/simulate.py: unchanged required
- synapse/ui/read_model.py: unchanged required
