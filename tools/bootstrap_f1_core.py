#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional


MARKER = "F1_CORE_BOOTSTRAP_2026_02"
DEFAULT_DIRS = ["synapse/infra", "synapse/cli", "tests/f1_core"]


def write_file_if_absent(path: Path, content: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def ensure_pkg_init(dir_path: Path) -> None:
    init = dir_path / "__init__.py"
    write_file_if_absent(init, f'"""AUTO: {MARKER}"""\n')


FEATURE_FLAGS_PY = '''\
"""Feature flags via environment variables. AUTO: F1_CORE_BOOTSTRAP_2026_02"""

from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Dict

def _parse_bool(v: str) -> bool:
    v = v.strip().lower()
    return v in ("1","true","yes","y","on")

@dataclass(frozen=True)
class FeatureFlags:
    values: Dict[str, bool]

    @staticmethod
    def load(prefix: str = "SYNAPSE_FLAG_") -> "FeatureFlags":
        out: Dict[str, bool] = {}
        for k, v in os.environ.items():
            if k.startswith(prefix):
                name = k[len(prefix):].strip().lower()
                out[name] = _parse_bool(v)
        return FeatureFlags(values=out)

    def is_on(self, name: str, default: bool = False) -> bool:
        return self.values.get(name.strip().lower(), default)
'''


SECRETS_MANAGER_PY = '''\
"""Secrets manager (env-only) with fail-fast. AUTO: F1_CORE_BOOTSTRAP_2026_02"""

from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Dict, Iterable

class MissingSecretError(RuntimeError):
    pass

@dataclass(frozen=True)
class Secrets:
    values: Dict[str, str]

    def get(self, key: str) -> str:
        if key not in self.values or not self.values[key]:
            raise MissingSecretError(f"MISSING_SECRET={key}")
        return self.values[key]

def load_required(required: Iterable[str]) -> Secrets:
    req = list(required)
    out: Dict[str, str] = {}
    missing = []
    for k in req:
        v = os.environ.get(k, "")
        if not v:
            missing.append(k)
        else:
            out[k] = v
    if missing:
        raise MissingSecretError("MISSING_SECRET=" + ",".join(missing))
    return Secrets(values=out)
'''


RETRY_POLICY_PY = '''\
"""Central retry policy with exponential backoff + jitter. AUTO: F1_CORE_BOOTSTRAP_2026_02"""

from __future__ import annotations
import random
import time
from dataclasses import dataclass
from typing import Callable, TypeVar, Tuple

T = TypeVar("T")

@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    base_delay_s: float
    max_delay_s: float

    def run(self, fn: Callable[[], T], retry_on: Tuple[type, ...] = (Exception,)) -> T:
        attempt = 0
        last_err: Exception | None = None
        while attempt < self.max_attempts:
            attempt += 1
            try:
                return fn()
            except retry_on as e:
                last_err = e
                if attempt >= self.max_attempts:
                    raise
                exp = self.base_delay_s * (2 ** (attempt - 1))
                delay = min(self.max_delay_s, exp)
                delay = delay * (0.7 + random.random() * 0.6)
                time.sleep(delay)
        raise last_err or RuntimeError("retry_policy_failed")
'''


CIRCUIT_BREAKER_PY = '''\
"""Simple circuit breaker. AUTO: F1_CORE_BOOTSTRAP_2026_02"""

from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Callable, TypeVar

T = TypeVar("T")

class CircuitOpenError(RuntimeError):
    pass

@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    reset_timeout_s: float = 30.0
    _failures: int = 0
    _opened_at: float | None = None

    def _is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if (time.time() - self._opened_at) >= self.reset_timeout_s:
            return False
        return True

    def call(self, fn: Callable[[], T]) -> T:
        if self._is_open():
            raise CircuitOpenError("circuit_open")
        try:
            out = fn()
            self._failures = 0
            self._opened_at = None
            return out
        except Exception:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._opened_at = time.time()
            raise
'''


IDEMPOTENCY_STORE_PY = '''\
"""File-backed idempotency store (JSON). AUTO: F1_CORE_BOOTSTRAP_2026_02"""

from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

@dataclass
class IdempotencyStore:
    path: Path
    _data: Dict[str, str]

    @staticmethod
    def open(path: str | Path) -> "IdempotencyStore":
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8") or "{}")
        else:
            raw = {}
            p.write_text("{}", encoding="utf-8")
        if not isinstance(raw, dict):
            raise ValueError("idempotency_store_corrupt")
        return IdempotencyStore(path=p, _data={str(k): str(v) for k, v in raw.items()})

    def has(self, key: str) -> bool:
        return key in self._data

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def put(self, key: str, value: str) -> None:
        self._data[key] = value
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
'''


LEDGER_PY = '''\
"""Append-only NDJSON ledger. AUTO: F1_CORE_BOOTSTRAP_2026_02"""

from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import time

def _now_iso_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

@dataclass
class Ledger:
    path: Path

    @staticmethod
    def open(path: str | Path) -> "Ledger":
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text("", encoding="utf-8")
        return Ledger(path=p)

    def append(self, event_type: str, correlation_id: str, idempotency_key: str,
               severity: str = "INFO", payload: Optional[Dict[str, Any]] = None) -> None:
        rec = {
            "ts": _now_iso_utc(),
            "event_type": str(event_type),
            "correlation_id": str(correlation_id),
            "idempotency_key": str(idempotency_key),
            "severity": str(severity),
            "payload": payload or {},
        }
        line = json.dumps(rec, ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\\n")
'''


HEALTHCHECK_PY = '''\
"""Healthcheck JSON (parseable). AUTO: F1_CORE_BOOTSTRAP_2026_02"""

from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any, Dict

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    out: Dict[str, Any] = {"ok": True, "checks": {}}
    out["checks"]["cwd"] = str(Path(".").resolve())

    try:
        from synapse.infra.feature_flags import FeatureFlags
        flags = FeatureFlags.load()
        out["checks"]["flags_loaded"] = True
        out["checks"]["flags_count"] = len(flags.values)
    except Exception as e:
        out["ok"] = False
        out["checks"]["flags_loaded"] = False
        out["checks"]["flags_error"] = str(e)

    try:
        import synapse.infra.doctor as _doctor  # noqa: F401
        out["checks"]["doctor_import"] = True
    except Exception as e:
        out["checks"]["doctor_import"] = False
        out["checks"]["doctor_error"] = str(e)

    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        print("HEALTHCHECK_OK=" + ("1" if out["ok"] else "0"))
        print(json.dumps(out, ensure_ascii=False, indent=2))

    return 0 if out["ok"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
'''


COCKPIT_PY = '''\
"""CLI cockpit minimal (health). AUTO: F1_CORE_BOOTSTRAP_2026_02"""

from __future__ import annotations
import argparse
import json
import subprocess
import sys

def _run(cmd: list[str]) -> dict:
    p = subprocess.run(cmd, capture_output=True, text=True)
    return {"cmd": cmd, "returncode": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="synapse-cli-cockpit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_health = sub.add_parser("health")
    p_health.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "health":
        res = _run([sys.executable, "-m", "synapse.infra.healthcheck", "--json"])
        out = {"ok": res["returncode"] == 0, "healthcheck": res}
        print(json.dumps(out, ensure_ascii=False) if args.json else json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out["ok"] else 2

    return 2

if __name__ == "__main__":
    raise SystemExit(main())
'''


TESTS_PY = '''\
import json
from pathlib import Path

def test_feature_flags_load_defaults():
    from synapse.infra.feature_flags import FeatureFlags
    flags = FeatureFlags.load()
    assert isinstance(flags.values, dict)

def test_idempotency_store_roundtrip(tmp_path: Path):
    from synapse.infra.idempotency_store import IdempotencyStore
    p = tmp_path / "idempo.json"
    s = IdempotencyStore.open(p)
    assert s.has("k") is False
    s.put("k", "v1")
    s2 = IdempotencyStore.open(p)
    assert s2.has("k") is True
    assert s2.get("k") == "v1"

def test_ledger_append(tmp_path: Path):
    from synapse.infra.ledger import Ledger
    p = tmp_path / "ledger.ndjson"
    l = Ledger.open(p)
    l.append("test.event", "corr1", "idem1", payload={"a": 1})
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["event_type"] == "test.event"
    assert rec["correlation_id"] == "corr1"
    assert rec["idempotency_key"] == "idem1"
    assert rec["payload"]["a"] == 1
'''


def generate(root: Path) -> None:
    for d in DEFAULT_DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)
        if d.startswith("synapse/"):
            ensure_pkg_init(root / d)

    write_file_if_absent(root / "synapse/infra/feature_flags.py", FEATURE_FLAGS_PY)
    write_file_if_absent(root / "synapse/infra/secrets_manager.py", SECRETS_MANAGER_PY)
    write_file_if_absent(root / "synapse/infra/retry_policy.py", RETRY_POLICY_PY)
    write_file_if_absent(root / "synapse/infra/circuit_breaker.py", CIRCUIT_BREAKER_PY)
    write_file_if_absent(root / "synapse/infra/idempotency_store.py", IDEMPOTENCY_STORE_PY)
    write_file_if_absent(root / "synapse/infra/ledger.py", LEDGER_PY)
    write_file_if_absent(root / "synapse/infra/healthcheck.py", HEALTHCHECK_PY)

    (root / "synapse/cli").mkdir(parents=True, exist_ok=True)
    ensure_pkg_init(root / "synapse/cli")
    write_file_if_absent(root / "synapse/cli/cockpit.py", COCKPIT_PY)

    write_file_if_absent(root / "tests/f1_core/test_f1_core_scaffold.py", TESTS_PY)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    generate(root)
    print(f"{MARKER}:OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
