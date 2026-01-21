from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9\s]+")


def normalize_text(s: str) -> str:
    """
    Deterministic normalization for similarity checks:
    - lower
    - strip accents
    - remove punctuation
    - collapse whitespace
    """
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = _NON_ALNUM.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    return s


def token_set(s: str) -> set[str]:
    n = normalize_text(s)
    if not n:
        return set()
    return set(n.split(" "))


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a.intersection(b))
    union = len(a.union(b))
    return float(inter) / float(union) if union else 0.0


@dataclass(frozen=True)
class DedupResult:
    kept: list[dict[str, Any]]
    dropped: int


def dedup_creatives(
    creatives: list[dict[str, Any]],
    *,
    key: str = "primary_text",
    threshold: float = 0.85,
) -> DedupResult:
    """
    Keeps order. Drops items similar to any already-kept item (Jaccard token similarity).
    """
    kept: list[dict[str, Any]] = []
    kept_tokens: list[set[str]] = []
    dropped = 0

    for c in creatives:
        txt = str(c.get(key) or "")
        ts = token_set(txt)

        is_dup = False
        for kt in kept_tokens:
            if jaccard(ts, kt) >= threshold:
                is_dup = True
                break

        if is_dup:
            dropped += 1
            continue

        kept.append(c)
        kept_tokens.append(ts)

    return DedupResult(kept=kept, dropped=dropped)
