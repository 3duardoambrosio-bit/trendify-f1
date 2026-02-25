from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given, strategies as st

from synapse.safety.audit import AuditTrail


# Contracts in AuditTrail.append require non-empty, non-whitespace identifiers.
# Keep strategies in the "safe id" lane so Hypothesis doesn't intentionally violate preconditions.
SAFE_ID = st.from_regex(r"[A-Za-z0-9][A-Za-z0-9_-]{0,15}", fullmatch=True)

ET = SAFE_ID
ACTOR = SAFE_ID
CID = SAFE_ID

PRINTABLE = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
    min_size=0,
    max_size=20,
)
KEY = st.from_regex(r"[A-Za-z][A-Za-z0-9_]{0,9}", fullmatch=True)
DATA = st.dictionaries(keys=KEY, values=PRINTABLE, min_size=0, max_size=5)
EVENTS = st.lists(st.tuples(ET, DATA, ACTOR, CID), min_size=1, max_size=6)


@given(EVENTS)
def test_append_and_verify_hash_chain(events) -> None:
    with TemporaryDirectory() as td:
        p = Path(td) / "events.ndjson"
        at = AuditTrail(str(p))
        for (et, data, actor, cid) in events:
            _ = at.append(et, data, actor=actor, correlation_id=cid)
        assert at.verify() is True

def test_verify_detects_tampered_hash() -> None:
    """Si se altera un hash en el archivo, verify debe retornar False."""
    import json
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from synapse.safety.audit import AuditTrail

    with TemporaryDirectory() as td:
        p = Path(td) / "events.ndjson"
        at = AuditTrail(str(p))
        at.append("evt1", {"k": "v"}, actor="a", correlation_id="c1")
        at.append("evt2", {"k": "v2"}, actor="a", correlation_id="c2")
        # Tamper: change hash of first event
        lines = p.read_text(encoding="utf-8").strip().split("\n")
        obj = json.loads(lines[0])
        obj["hash"] = "0" * 64
        lines[0] = json.dumps(obj, sort_keys=True, separators=(",", ":"))
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        assert at.verify() is False


def test_verify_empty_file_returns_true() -> None:
    """Archivo vacío o inexistente → verify True (cadena vacía es válida)."""
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from synapse.safety.audit import AuditTrail

    with TemporaryDirectory() as td:
        at = AuditTrail(str(Path(td) / "nonexistent.ndjson"))
        assert at.verify() is True
