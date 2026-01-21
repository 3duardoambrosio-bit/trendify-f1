import os
from pathlib import Path
import pytest

from synapse.infra.secrets import Secrets, SecretMissing
from synapse.infra.config_validator import ConfigSpec, ConfigValidator


def test_dotenv_loaded_and_env_overrides(tmp_path: Path, monkeypatch):
    p = tmp_path / ".env"
    p.write_text("A=from_dotenv\nB=dotenv\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("B", "from_env")

    s = Secrets(dotenv_path=Path(".env"))
    assert s.get("A") == "from_dotenv"
    assert s.get("B") == "from_env"


def test_require_missing_raises(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = Secrets(dotenv_path=Path(".env"))
    with pytest.raises(SecretMissing):
        s.require("NOPE_123")


def test_config_validator_missing_and_wrong_type():
    spec = ConfigSpec(required={"api_key": str}, optional={"timeout_s": float})
    v = ConfigValidator(spec)

    res = v.validate({"timeout_s": "10"})
    assert res.ok is False
    assert "api_key" in res.missing
    assert "timeout_s" in res.wrong_type
