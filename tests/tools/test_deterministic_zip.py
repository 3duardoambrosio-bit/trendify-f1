from __future__ import annotations

import importlib.util
import os
import time
from pathlib import Path
from zipfile import ZipFile

import pytest


MODULE_PATH = Path(__file__).resolve().parents[2] / "tools" / "deterministic_zip.py"


def load_module():
    spec = importlib.util.spec_from_file_location("deterministic_zip", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_create_deterministic_zip_reproducible(tmp_path):
    module = load_module()

    source = tmp_path / "source"
    source.mkdir()

    (source / "b.txt").write_bytes(b"bravo\n")
    nested = source / "nested"
    nested.mkdir()
    (nested / "a.txt").write_bytes(b"alpha\n")

    old_time = 946684800
    new_time = 1700000000
    os.utime(source / "b.txt", (old_time, old_time))
    os.utime(nested / "a.txt", (new_time, new_time))

    zip_a = tmp_path / "a.zip"
    zip_b = tmp_path / "b.zip"

    module.create_deterministic_zip(source, zip_a)
    time.sleep(1.1)
    module.create_deterministic_zip(source, zip_b)

    assert module.sha256_file(zip_a) == module.sha256_file(zip_b)

    with ZipFile(zip_a) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]

        assert names == sorted(names)
        assert names == ["b.txt", "nested/a.txt"]
        assert {info.date_time for info in infos} == {module.FIXED_ZIP_DATE_TIME}
        assert archive.read("b.txt") == b"bravo\n"
        assert archive.read("nested/a.txt") == b"alpha\n"


def test_create_deterministic_zip_rejects_output_inside_source(tmp_path):
    module = load_module()

    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_bytes(b"alpha\n")

    with pytest.raises(ValueError, match="outside source directory"):
        module.create_deterministic_zip(source, source / "bad.zip")