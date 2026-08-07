"""A8-R30 contract tests for the full audit bundle builder.

This test intentionally runs the bundle builder with -SkipHeavy to avoid recursive
pytest execution while still validating the durable evidence contract added in A8-R29.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path


TEXT_SUFFIXES = {
    ".txt",
    ".json",
    ".md",
    ".csv",
    ".ps1",
    ".psm1",
    ".psd1",
    ".log",
    ".ini",
    ".yaml",
    ".yml",
    ".toml",
}

REQUIRED_ENTRIES = {
    "bundle_encoding_audit.txt",
    "post_commit_bom_scan.txt",
    "git_show_head_name_only.txt",
    "summary.txt",
    "source_snapshots/scripts__gate_f1.ps1",
    "source_snapshots/scripts__run_pytest_stable.ps1",
    "source_snapshots/tools__build_full_audit_bundle.ps1",
}

REQUIRED_BUILDER_MARKERS = {
    "Write-A8R29Utf8NoBomText",
    "Convert-A8R29EvidenceTextFilesToUtf8NoBom",
    "bundle_encoding_audit.txt",
    "post_commit_bom_scan.txt",
    "git_show_head_name_only.txt",
    "rev-list --parents -n 1 HEAD",
    'diff --name-only "HEAD^1" HEAD',
    "HOOK_SMOKE_NOT_RUN_BY_BUNDLE_BUILDER=1",
    "HOOK_SMOKE_RC_SEMANTIC=NA",
    "source_snapshots",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def normalize_entry(name: str) -> str:
    return name.replace("\\", "/")


def is_text_evidence(entry_name: str) -> bool:
    normalized = normalize_entry(entry_name)
    name = Path(normalized).name.lower()
    suffix = Path(normalized).suffix.lower()
    return suffix in TEXT_SUFFIXES or name.endswith(".rc")


def has_utf8_bom(data: bytes) -> bool:
    return len(data) >= 3 and data[:3] == b"\xef\xbb\xbf"


def has_utf16_bom(data: bytes) -> bool:
    return len(data) >= 2 and data[:2] in {b"\xff\xfe", b"\xfe\xff"}


def looks_utf16_like(data: bytes) -> bool:
    if len(data) <= 20:
        return False
    sample = data[: min(len(data), 200)]
    zero_count = sample.count(0)
    return zero_count >= len(sample) // 4


def read_zip_text(
    zf: zipfile.ZipFile,
    normalized_to_raw: dict[str, str],
    normalized_name: str,
) -> str:
    raw_name = normalized_to_raw[normalized_name]
    return zf.read(raw_name).decode("utf-8")


def test_full_audit_bundle_contract_skipheavy_is_clean_and_auditable() -> None:
    repo = repo_root()
    builder = repo / "tools" / "build_full_audit_bundle.ps1"
    assert builder.exists(), f"missing builder: {builder}"

    powershell = (
        shutil.which("pwsh")
        or shutil.which("powershell")
        or shutil.which("powershell.exe")
    )
    assert powershell, "PowerShell executable is required for bundle contract validation"

    temp_root = Path("C:/Temp") if os.name == "nt" else Path(tempfile.gettempdir())
    out_dir = temp_root / f"synapse_a8_r30_bundle_contract_{os.getpid()}"
    zip_path = temp_root / f"synapse_a8_r30_bundle_contract_{os.getpid()}.zip"

    if out_dir.exists():
        shutil.rmtree(out_dir)
    if zip_path.exists():
        zip_path.unlink()

    command = [
        powershell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(builder),
        "-Repo",
        str(repo),
        "-OutDir",
        str(out_dir),
        "-ZipPath",
        str(zip_path),
        "-SkipHeavy",
    ]

    env = os.environ.copy()
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONPATH"] = ""
    env["SYNAPSE_A8_R30_BUNDLE_CONTRACT"] = "1"

    result = subprocess.run(
        command,
        cwd=repo,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=180,
        check=False,
    )

    assert result.returncode == 0, (
        "bundle builder failed\n"
        f"rc={result.returncode}\n"
        f"stdout_tail={result.stdout[-4000:]}\n"
        f"stderr_tail={result.stderr[-4000:]}"
    )
    assert zip_path.exists(), f"bundle zip was not created: {zip_path}"
    assert "FULL_AUDIT_BUNDLE_PASS=1" in result.stdout

    with zipfile.ZipFile(zip_path) as zf:
        raw_names = zf.namelist()
        normalized_to_raw = {normalize_entry(name): name for name in raw_names}
        normalized_names = set(normalized_to_raw)

        missing = sorted(REQUIRED_ENTRIES - normalized_names)
        assert not missing, f"missing required bundle entries: {missing}"

        source_snapshots = [
            name for name in normalized_names if name.startswith("source_snapshots/")
        ]
        assert len(source_snapshots) >= 3, source_snapshots

        utf8_bom = []
        utf16_bom = []
        utf16_like = []

        for raw_name in raw_names:
            if not is_text_evidence(raw_name):
                continue
            data = zf.read(raw_name)
            normalized = normalize_entry(raw_name)
            if has_utf8_bom(data):
                utf8_bom.append(normalized)
            if has_utf16_bom(data):
                utf16_bom.append(normalized)
            if looks_utf16_like(data):
                utf16_like.append(normalized)

        assert utf8_bom == [], f"UTF-8 BOM files found in bundle: {utf8_bom}"
        assert utf16_bom == [], f"UTF-16 BOM files found in bundle: {utf16_bom}"
        assert utf16_like == [], f"UTF-16-like text evidence found in bundle: {utf16_like}"

        encoding_audit = read_zip_text(
            zf, normalized_to_raw, "bundle_encoding_audit.txt"
        )
        assert "A8_R29_BUNDLE_ENCODING_AUDIT=1" in encoding_audit
        assert "BOM_AFTER_COUNT=0" in encoding_audit
        assert "UTF16_BOM_AFTER_COUNT=0" in encoding_audit

        post_commit_bom_scan = read_zip_text(
            zf, normalized_to_raw, "post_commit_bom_scan.txt"
        )
        assert "A8_R29_POST_COMMIT_BOM_SCAN=1" in post_commit_bom_scan
        assert "BOM_BAD_COUNT=0" in post_commit_bom_scan

        summary = read_zip_text(zf, normalized_to_raw, "summary.txt")
        assert "FULL_AUDIT_BUNDLE_PASS=1" in summary
        assert "SKIP_HEAVY=1" in summary

        git_show = read_zip_text(zf, normalized_to_raw, "git_show_head_name_only.txt")
        assert git_show.strip(), "git_show_head_name_only.txt must not be empty"

        hook_stdout = read_zip_text(zf, normalized_to_raw, "hook_smoke.stdout.txt")
        hook_rc = read_zip_text(zf, normalized_to_raw, "hook_smoke.rc.txt").strip()

        if "HOOK_SMOKE_NOT_RUN_BY_BUNDLE_BUILDER=1" in hook_stdout:
            assert hook_rc != "0", "hook smoke not-run state must not look like rc=0"
            hook_status = read_zip_text(
                zf, normalized_to_raw, "hook_smoke.status.txt"
            )
            assert "HOOK_SMOKE_RC_SEMANTIC=NA" in hook_status

        if "SKIPPED_BY_SKIPHEAVY=1" in hook_stdout:
            assert hook_rc == "0"
            assert "SKIP_HEAVY=1" in summary


def test_full_audit_bundle_builder_contains_durable_contract_markers() -> None:
    repo = repo_root()
    builder = repo / "tools" / "build_full_audit_bundle.ps1"
    builder_text = builder.read_text(encoding="utf-8-sig")

    missing_markers = [
        marker for marker in sorted(REQUIRED_BUILDER_MARKERS)
        if marker not in builder_text
    ]
    assert missing_markers == [], (
        "builder lost durable A8-R29/A8-R30 contract markers: "
        f"{missing_markers}"
    )



def test_merge_head_name_only_contract_uses_first_parent_diff() -> None:
    builder = (
        repo_root()
        / "tools"
        / "build_full_audit_bundle.ps1"
    )

    builder_text = builder.read_text(
        encoding="utf-8-sig",
    )

    assert "rev-list --parents -n 1 HEAD" in builder_text
    assert 'diff --name-only "HEAD^1" HEAD' in builder_text

    temp_root = (
        Path("C:/Temp")
        if os.name == "nt"
        else Path(tempfile.gettempdir())
    )

    with tempfile.TemporaryDirectory(
        prefix="synapse_a8_r30_merge_",
        dir=temp_root,
    ) as temporary:
        synthetic_repo = Path(temporary) / "repo"
        synthetic_repo.mkdir()

        def run_git(
            *arguments: str,
        ) -> subprocess.CompletedProcess[str]:
            result = subprocess.run(
                ["git", *arguments],
                cwd=synthetic_repo,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

            assert result.returncode == 0, (
                f"git failed: {arguments}\n"
                f"stdout={result.stdout}\n"
                f"stderr={result.stderr}"
            )

            return result

        run_git("init", "-q")
        run_git(
            "config",
            "user.email",
            "a8-r30@example.invalid",
        )
        run_git(
            "config",
            "user.name",
            "A8 R30 Regression",
        )

        base_marker = synthetic_repo / "base.txt"
        base_marker.write_text(
            "base\n",
            encoding="utf-8",
            newline="\n",
        )

        run_git("add", "base.txt")
        run_git("commit", "-q", "-m", "base")

        base_head = run_git(
            "rev-parse",
            "HEAD",
        ).stdout.strip()

        run_git(
            "checkout",
            "-q",
            "-b",
            "synthetic-side",
        )

        side_marker = synthetic_repo / "side.txt"
        side_marker.write_text(
            "side\n",
            encoding="utf-8",
            newline="\n",
        )

        run_git("add", "side.txt")
        run_git("commit", "-q", "-m", "side")

        run_git(
            "checkout",
            "-q",
            "-b",
            "synthetic-main",
            base_head,
        )

        main_marker = synthetic_repo / "main.txt"
        main_marker.write_text(
            "main\n",
            encoding="utf-8",
            newline="\n",
        )

        run_git("add", "main.txt")
        run_git("commit", "-q", "-m", "main")

        run_git(
            "merge",
            "-q",
            "--no-ff",
            "synthetic-side",
            "-m",
            "synthetic merge",
        )

        parent_record = run_git(
            "rev-list",
            "--parents",
            "-n",
            "1",
            "HEAD",
        ).stdout.split()

        assert len(parent_record) == 3

        legacy_names = run_git(
            "show",
            "--name-only",
            "--pretty=format:",
            "HEAD",
        ).stdout.strip()

        assert legacy_names == ""

        first_parent_names = {
            line.strip()
            for line in run_git(
                "diff",
                "--name-only",
                "HEAD^1",
                "HEAD",
            ).stdout.splitlines()
            if line.strip()
        }

        assert first_parent_names == {"side.txt"}
