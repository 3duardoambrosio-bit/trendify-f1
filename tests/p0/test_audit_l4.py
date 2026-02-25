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
