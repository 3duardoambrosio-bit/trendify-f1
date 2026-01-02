# synapse/reporting/__init__.py
# No importar módulos con CLI aquí.
from .audit_viewer import AuditQuery, query_events, render_markdown, write_report
__all__ = ["AuditQuery", "query_events", "render_markdown", "write_report"]
