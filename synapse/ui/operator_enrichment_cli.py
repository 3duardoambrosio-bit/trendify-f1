"""A8-R111 operator enrichment CLI.

Commands:
- template: create one empty local enrichment JSON for an existing candidate.
- rebuild: rebuild the offline workspace and apply local enrichment files.

No network, no external writes, no credentials, no spend, no publication.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from synapse.integration.operator_enrichment import (
    EnrichmentApplication,
    OperatorEnrichmentError,
    apply_enrichment_file,
    write_enrichment_template,
)
from synapse.ui.local_catalog_workspace import (
    CatalogIntakeError,
    CatalogIntakeResult,
    build_intake_report,
    parse_catalog_csv,
)
from synapse.ui.operator_workbench_renderer import scan_forbidden_tokens
from synapse.ui.operator_workbench_view_model import build_view_model
from synapse.ui.operator_workbench_visual import render_workspace_html

DEFAULT_WORKSPACE = Path("artifacts/a8_r111_operator_enrichment")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _clear_generated_outputs(workspace: Path) -> None:
    workspace_path = workspace / "workspace.html"
    if workspace_path.exists() or workspace_path.is_symlink():
        workspace_path.unlink()

    report_path = workspace / "intake_report.json"
    if report_path.exists() or report_path.is_symlink():
        report_path.unlink()

    candidates_dir = workspace / "candidates"
    if candidates_dir.is_symlink():
        candidates_dir.unlink()
        return
    if not candidates_dir.exists():
        return

    for path in sorted(candidates_dir.glob("*.json")):
        if path.is_file() or path.is_symlink():
            path.unlink()


def _application_record(application: EnrichmentApplication) -> dict[str, Any]:
    fixture_id = str(application.fixture.get("fixture_id") or "")
    return {
        "fixture_id": fixture_id,
        "status": application.status,
        "richness": application.richness,
        "missing_fields": list(application.missing_fields),
        "errors": list(application.errors),
        "methodology_status": application.methodology_status,
    }


def rebuild_workspace(
    csv_path: str | Path,
    workspace: str | Path = DEFAULT_WORKSPACE,
) -> dict[str, Any]:
    result = parse_catalog_csv(csv_path)
    root = Path(workspace)
    root.mkdir(parents=True, exist_ok=True)
    _clear_generated_outputs(root)

    input_dir = root / "candidates_input"
    candidates_dir = root / "candidates"
    input_dir.mkdir(parents=True, exist_ok=True)
    candidates_dir.mkdir(parents=True, exist_ok=True)

    applications: list[EnrichmentApplication] = []
    enriched_fixtures: list[Mapping[str, Any]] = []

    for fixture in sorted(result.fixtures, key=lambda item: str(item["fixture_id"])):
        fixture_id = str(fixture["fixture_id"])
        enrichment_path = input_dir / f"{fixture_id}.enrichment.json"
        application = apply_enrichment_file(
            fixture,
            enrichment_path if enrichment_path.is_file() else None,
        )
        applications.append(application)
        enriched_fixtures.append(application.fixture)

    enriched_result = CatalogIntakeResult(
        csv_name=result.csv_name,
        rows=result.rows,
        fixtures=tuple(enriched_fixtures),
    )

    report = build_intake_report(result)
    status_counts: dict[str, int] = {}
    for application in applications:
        status_counts[application.status] = status_counts.get(application.status, 0) + 1

    report["operator_enrichment"] = {
        "schema_version": "a8-r111.operator_enrichment_report.v1",
        "counts": dict(sorted(status_counts.items())),
        "candidates": [
            _application_record(application)
            for application in sorted(
                applications,
                key=lambda item: str(item.fixture.get("fixture_id") or ""),
            )
        ],
        "boundaries": {
            "no_network": True,
            "no_live_writes": True,
            "no_spend": True,
            "operator_in_control": True,
            "deterministic": True,
        },
    }

    report_path = root / "intake_report.json"
    _write_json(report_path, report)

    fixture_paths: list[Path] = []
    for fixture in enriched_result.fixtures:
        target = candidates_dir / f"{fixture['fixture_id']}.json"
        _write_json(target, fixture)
        fixture_paths.append(target)

    workspace_path: Path | None = None
    if enriched_result.fixtures:
        view_models = [
            build_view_model(
                fixture,
                source_fixture=f"{result.csv_name}#{fixture['fixture_id']}",
            )
            for fixture in sorted(
                enriched_result.fixtures,
                key=lambda item: str(item["fixture_id"]),
            )
        ]
        document = render_workspace_html(view_models)
        forbidden = scan_forbidden_tokens(document)
        if forbidden:
            raise OperatorEnrichmentError(
                "forbidden_tokens_in_workspace=" + ",".join(forbidden)
            )
        workspace_path = root / "workspace.html"
        with workspace_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(document)

    return {
        "counts": report["counts"],
        "enrichment_counts": report["operator_enrichment"]["counts"],
        "report_path": report_path,
        "workspace_path": workspace_path,
        "fixture_paths": fixture_paths,
        "input_dir": input_dir,
    }


def create_template(
    workspace: str | Path,
    fixture_id: str,
    *,
    overwrite: bool = False,
) -> Path:
    root = Path(workspace)
    candidate_path = root / "candidates" / f"{fixture_id}.json"
    if not candidate_path.is_file():
        raise OperatorEnrichmentError(
            f"candidate_fixture_not_found={candidate_path.as_posix()}"
        )

    try:
        fixture = json.loads(candidate_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OperatorEnrichmentError("candidate_fixture_invalid_json") from exc

    if str(fixture.get("fixture_id") or "") != fixture_id:
        raise OperatorEnrichmentError(
            "candidate fixture_id does not match requested fixture_id"
        )

    target = root / "candidates_input" / f"{fixture_id}.enrichment.json"
    return write_enrichment_template(
        target,
        fixture_id,
        overwrite=overwrite,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m synapse.ui.operator_enrichment_cli",
        description=(
            "A8-R111 local operator enrichment and deterministic workspace rebuild."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    template = subparsers.add_parser(
        "template",
        help="Create one empty enrichment template for an existing candidate.",
    )
    template.add_argument("--workspace", required=True)
    template.add_argument("--fixture-id", required=True)
    template.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing template. Never use this after operator edits.",
    )

    rebuild = subparsers.add_parser(
        "rebuild",
        help="Rebuild the workspace using local enrichment files when present.",
    )
    rebuild.add_argument("--csv", required=True)
    rebuild.add_argument(
        "--workspace",
        default=str(DEFAULT_WORKSPACE),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "template":
            target = create_template(
                args.workspace,
                args.fixture_id,
                overwrite=bool(args.force),
            )
            print(f"template={target.as_posix()}")
            print("network=false")
            print("live_write=false")
            print("real_spend=false")
            return 0

        summary = rebuild_workspace(args.csv, args.workspace)
    except (CatalogIntakeError, OperatorEnrichmentError) as exc:
        print(f"operator_enrichment_error={exc}")
        return 2

    print(f"report={Path(summary['report_path']).as_posix()}")
    if summary["workspace_path"] is None:
        print("workspace=NONE")
        return 3
    print(f"workspace={Path(summary['workspace_path']).as_posix()}")
    for status, count in sorted(summary["enrichment_counts"].items()):
        print(f"enrichment_{status.lower()}={count}")
    print("network=false")
    print("live_write=false")
    print("real_spend=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
