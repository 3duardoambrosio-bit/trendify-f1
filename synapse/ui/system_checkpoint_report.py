"""Deterministic, inert HTML report for the local system checkpoint.

The renderer is deliberately pure: it performs no filesystem access, network
access, publication, external write, or live action.  Callers remain
responsible for writing the returned UTF-8 text inside an authorized output
directory.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from html import escape
import math
import re
from typing import Any


class SystemCheckpointReportError(ValueError):
    """Raised when checkpoint report data is incomplete or unsafe."""


REPORT_SCHEMA_VERSION = "synapse.system_checkpoint_report.v1"


_SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("a-product", "A. Product", "product"),
    ("b-financial", "B. Financial evaluation", "financial"),
    ("c-decision", "C. Checkpoint decision", "decision"),
    ("d-methodology", "D. Methodology", "methodology"),
    ("e-customer-copy", "E. Customer copy", "customer_copy"),
    (
        "f-canonical-product",
        "F. Canonical product custody",
        "canonical_product",
    ),
    (
        "g-storefront-read-model",
        "G. Storefront read model",
        "storefront_read_model",
    ),
    ("h-shopify-boundary", "H. Shopify boundary", "shopify_boundary"),
    ("i-execution-trace", "I. Execution trace", "execution_trace"),
)

_DISPLAY_FLAGS: tuple[str, ...] = (
    "sample_input",
    "commercial_evidence",
    "offline_only",
    "external_write",
    "live_action",
    "published",
)

_SAFETY_FLAGS: tuple[tuple[str, bool], ...] = (
    ("commercial_evidence", False),
    ("offline_only", True),
    ("external_write", False),
    ("live_action", False),
    ("published", False),
)

_SHOPIFY_BOUNDARY: tuple[tuple[str, object], ...] = (
    ("shopify_mode", "draft_export"),
    ("published", False),
    ("external_write", False),
    ("shopify_api_called", False),
    ("operator_publication_approval", False),
)

_UNSAFE_SCHEME_RE = re.compile(
    r"(?i)\b(?:https?|ftp|javascript|data):[^\s<>'\"]*"
)
_PROTOCOL_RELATIVE_URL_RE = re.compile(
    r"(?<!:)(?<![\\/])//[a-z0-9][^\s<>'\"]*",
    flags=re.IGNORECASE,
)


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SystemCheckpointReportError(f"{path} must be a mapping")
    if any(not isinstance(key, str) for key in value):
        raise SystemCheckpointReportError(f"{path} keys must be strings")
    return value


def _require_exact_bool(
    value: Mapping[str, Any],
    key: str,
    expected: bool,
) -> None:
    actual = value.get(key)
    if actual is not expected:
        expected_text = str(expected).lower()
        raise SystemCheckpointReportError(
            f"report_data.{key} must be {expected_text}"
        )


def _validate_report_data(
    report_data: Mapping[str, Any],
) -> None:
    if "sample_input" not in report_data:
        raise SystemCheckpointReportError(
            "report_data missing required field: sample_input"
        )
    if not isinstance(report_data.get("sample_input"), bool):
        raise SystemCheckpointReportError(
            "report_data.sample_input must be a boolean"
        )

    for key, expected in _SAFETY_FLAGS:
        if key not in report_data:
            raise SystemCheckpointReportError(
                f"report_data missing required field: {key}"
            )
        _require_exact_bool(report_data, key, expected)

    for _section_id, _label, key in _SECTIONS:
        if key not in report_data:
            raise SystemCheckpointReportError(
                f"report_data missing required section: {key}"
            )

        value = report_data[key]
        if key == "execution_trace":
            if (
                isinstance(value, (str, bytes))
                or not isinstance(value, Sequence)
                or not value
            ):
                raise SystemCheckpointReportError(
                    "report_data.execution_trace must be a non-empty sequence"
                )
            for index, entry in enumerate(value):
                _require_mapping(
                    entry,
                    f"report_data.execution_trace[{index}]",
                )
        else:
            section = _require_mapping(
                value,
                f"report_data.{key}",
            )
            if not section:
                raise SystemCheckpointReportError(
                    f"report_data.{key} must not be empty"
                )

    shopify = _require_mapping(
        report_data["shopify_boundary"],
        "report_data.shopify_boundary",
    )
    for key, expected in _SHOPIFY_BOUNDARY:
        if shopify.get(key) != expected or (
            isinstance(expected, bool)
            and shopify.get(key) is not expected
        ):
            expected_text = (
                str(expected).lower()
                if isinstance(expected, bool)
                else str(expected)
            )
            raise SystemCheckpointReportError(
                "report_data.shopify_boundary."
                f"{key} must be {expected_text}"
            )


def _safe_text(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "".join(
        character
        if character in {"\n", "\t"} or ord(character) >= 32
        else "\N{REPLACEMENT CHARACTER}"
        for character in normalized
    )
    normalized = _UNSAFE_SCHEME_RE.sub(
        "[absolute URL omitted]",
        normalized,
    )
    normalized = _PROTOCOL_RELATIVE_URL_RE.sub(
        "[absolute URL omitted]",
        normalized,
    )
    return escape(normalized, quote=True)


def _render_scalar(value: Any, path: str) -> str:
    if value is None:
        text = "null"
    elif isinstance(value, bool):
        text = str(value).lower()
    elif isinstance(value, int):
        text = str(value)
    elif isinstance(value, Decimal):
        if not value.is_finite():
            raise SystemCheckpointReportError(
                f"{path} must contain only finite decimals"
            )
        text = str(value)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise SystemCheckpointReportError(
                f"{path} must contain only finite numbers"
            )
        text = repr(value)
    elif isinstance(value, str):
        text = value
    else:
        raise SystemCheckpointReportError(
            f"{path} contains unsupported value type "
            f"{type(value).__name__}"
        )

    return f'<span class="value">{_safe_text(text)}</span>'


def _render_value(value: Any, path: str) -> str:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise SystemCheckpointReportError(
                f"{path} keys must be strings"
            )
        if not value:
            return '<p class="empty">{}</p>'

        rows: list[str] = ['<dl class="data">']
        for key in sorted(value):
            rows.append(f"<dt>{_safe_text(key)}</dt>")
            rows.append(
                "<dd>"
                + _render_value(value[key], f"{path}.{key}")
                + "</dd>"
            )
        rows.append("</dl>")
        return "".join(rows)

    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes),
    ):
        if not value:
            return '<p class="empty">[]</p>'

        items = ['<ol class="sequence">']
        for index, item in enumerate(value):
            items.append(
                "<li>"
                + _render_value(item, f"{path}[{index}]")
                + "</li>"
            )
        items.append("</ol>")
        return "".join(items)

    return _render_scalar(value, path)


def render_system_checkpoint_report(
    report_data: Mapping[str, Any],
) -> str:
    """Render one deterministic local-only checkpoint operator report."""

    data = _require_mapping(report_data, "report_data")
    _validate_report_data(data)

    sample_banner = (
        "SAMPLE INPUT — NOT COMMERCIAL EVIDENCE"
        if data["sample_input"] is True
        else "USER-SUPPLIED INPUT — NOT COMMERCIAL EVIDENCE"
    )

    sections = []
    for section_id, label, key in _SECTIONS:
        sections.append(
            f'<section id="{section_id}" data-checkpoint-section="{key}">'
            f"<h2>{label}</h2>"
            f"{_render_value(data[key], f'report_data.{key}')}"
            "</section>"
        )

    flags = "".join(
        "<li><code>"
        + _safe_text(key)
        + "="
        + _safe_text(str(data[key]).lower())
        + "</code></li>"
        for key in _DISPLAY_FLAGS
    )

    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        "<title>SYNAPSE local system checkpoint</title>\n"
        "<style>\n"
        ":root{color-scheme:light;--ink:#172033;--muted:#526071;"
        "--line:#d6dce5;--safe:#0b6b3a;--warn:#8a4b08;--paper:#fff;}"
        "*{box-sizing:border-box}body{margin:0;background:#f4f6f9;"
        "color:var(--ink);font:15px/1.5 system-ui,sans-serif}"
        "main{max-width:1080px;margin:0 auto;padding:32px 20px 64px}"
        "header,section{background:var(--paper);border:1px solid var(--line);"
        "border-radius:8px;padding:20px;margin:0 0 16px}"
        "h1,h2{line-height:1.2;margin-top:0}h1{font-size:28px}"
        "h2{font-size:20px}.boundary{color:var(--safe);font-weight:800;"
        "letter-spacing:.04em}.sample{color:var(--warn);font-weight:800;"
        "border:2px solid currentColor;padding:10px}"
        ".disclaimer{color:var(--muted)}.flags{display:flex;flex-wrap:wrap;"
        "gap:8px;padding:0;list-style:none}.flags li{background:#eef2f7;"
        "border-radius:4px;padding:4px 8px}.data{display:grid;"
        "grid-template-columns:minmax(170px,1fr) minmax(0,3fr);"
        "gap:0;border-top:1px solid var(--line)}dt,dd{margin:0;"
        "padding:8px;border-bottom:1px solid var(--line)}dt{font-weight:700}"
        ".data .data{grid-column:1/-1}.sequence{margin:0;padding-left:24px}"
        ".sequence>li{margin:0 0 8px}.value{white-space:pre-wrap;"
        "overflow-wrap:anywhere}.empty{color:var(--muted);font-style:italic}"
        "code{font-family:ui-monospace,monospace}@media(max-width:700px){"
        ".data{grid-template-columns:1fr}dt{border-bottom:0;padding-bottom:0}}"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        "<main>\n"
        "<header>\n"
        "<h1>SYNAPSE system checkpoint — local operator report</h1>\n"
        '<p class="boundary">LOCAL-ONLY · NO LIVE ACTIONS · '
        "NO EXTERNAL WRITES · NOT PUBLISHED</p>\n"
        f'<p class="sample">{sample_banner}</p>\n'
        '<p class="disclaimer">This report does not authorize publication, '
        "spend, fulfillment, order forwarding, or any external integration."
        "</p>\n"
        f'<ul class="flags">{flags}</ul>\n'
        "</header>\n"
        + "\n".join(sections)
        + "\n</main>\n"
        "</body>\n"
        "</html>\n"
    )


__all__ = [
    "REPORT_SCHEMA_VERSION",
    "SystemCheckpointReportError",
    "render_system_checkpoint_report",
]
