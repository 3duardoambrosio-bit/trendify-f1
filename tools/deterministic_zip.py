from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

FIXED_ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)
FILE_MODE_0644 = 0o100644


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _as_resolved_dir(source_dir: str | Path) -> Path:
    source = Path(source_dir).resolve()
    if not source.exists():
        raise FileNotFoundError(f"source directory does not exist: {source}")
    if not source.is_dir():
        raise NotADirectoryError(f"source path is not a directory: {source}")
    return source


def _assert_output_outside_source(source: Path, output_zip: Path) -> None:
    try:
        output_zip.resolve().relative_to(source)
    except ValueError:
        return
    raise ValueError("output zip must be outside source directory")


def _iter_files(source: Path) -> list[Path]:
    return sorted(
        (path for path in source.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(source).as_posix(),
    )


def create_deterministic_zip(source_dir: str | Path, output_zip: str | Path) -> Path:
    source = _as_resolved_dir(source_dir)
    output = Path(output_zip).resolve()

    _assert_output_outside_source(source, output)

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    with ZipFile(output, mode="w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in _iter_files(source):
            relative_name = path.relative_to(source).as_posix()
            info = ZipInfo(filename=relative_name, date_time=FIXED_ZIP_DATE_TIME)
            info.compress_type = ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = FILE_MODE_0644 << 16

            archive.writestr(
                info,
                path.read_bytes(),
                compress_type=ZIP_DEFLATED,
                compresslevel=9,
            )

    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a deterministic zip from a directory."
    )
    parser.add_argument("source_dir")
    parser.add_argument("output_zip")
    args = parser.parse_args(argv)

    output = create_deterministic_zip(args.source_dir, args.output_zip)
    print("DETERMINISTIC_ZIP_CREATED=1")
    print(f"ZIP_PATH={output}")
    print(f"ZIP_SIZE_BYTES={output.stat().st_size}")
    print(f"ZIP_SHA256={sha256_file(output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())