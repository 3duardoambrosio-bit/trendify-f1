# tests/integration/test_secrets.py
import os
import tempfile

import pytest

from synapse.integration.secrets import SecretsVault, SecretSpec, SecretsError


def test_dotenv_parse_and_get(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, ".env")
        with open(p, "w", encoding="utf-8") as f:
            f.write("A=1\nB='two'\n#C=3\n")
        v = SecretsVault(dotenv_path=p, allow_dotenv=True)
        assert v.get("A") == "1"
        assert v.get("B") == "two"
        assert v.get("C") is None


def test_env_overrides_dotenv(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, ".env")
        with open(p, "w", encoding="utf-8") as f:
            f.write("TOKEN=from_dotenv\n")
        monkeypatch.setenv("TOKEN", "from_env")
        v = SecretsVault(dotenv_path=p, allow_dotenv=True)
        assert v.get("TOKEN") == "from_env"


def test_require_missing_raises():
    v = SecretsVault(allow_dotenv=False)
    with pytest.raises(SecretsError):
        v.require("NOPE", hint="ponlo en .env o env var")


def test_validate_specs():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, ".env")
        with open(p, "w", encoding="utf-8") as f:
            f.write("X=abc123\n")
        v = SecretsVault(dotenv_path=p, allow_dotenv=True)
        specs = (
            SecretSpec("X", required=True, validator=lambda s: len(s) >= 3, hint="min 3 chars"),
        )
        out = v.validate(specs)
        assert out["X"] == "abc123"
