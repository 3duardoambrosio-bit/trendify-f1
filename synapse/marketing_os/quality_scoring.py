from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from synapse.marketing_os.creative_dedup import normalize_text


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


@dataclass(frozen=True)
class CreativeQuality:
    score: int
    metrics: dict[str, Any]


def score_creatives(
    creatives: list[dict[str, Any]],
    *,
    title: str | None = None,
    text_key: str = "primary_text",
) -> CreativeQuality:
    n = len(creatives)
    texts = [str(c.get(text_key) or "") for c in creatives]
    norm = [normalize_text(t) for t in texts]

    uniq = len(set(norm)) if n else 0
    unique_ratio = (uniq / n) if n else 0.0

    lengths = [len(t) for t in texts if t]
    avg_len = (sum(lengths) / len(lengths)) if lengths else 0.0

    # title presence = at least one title token appears in creative text
    title_tokens = set(normalize_text(title or "").split()) if title else set()
    present = 0
    if title_tokens and n:
        for nt in norm:
            toks = set(nt.split())
            if toks.intersection(title_tokens):
                present += 1
    title_presence_ratio = (present / n) if n else 0.0

    # penalties: too short or too long average
    # sweet spot: ~35–140 chars
    short_pen = _clamp((35.0 - avg_len) / 35.0, 0.0, 1.0) if avg_len < 35.0 else 0.0
    long_pen = _clamp((avg_len - 140.0) / 140.0, 0.0, 1.0) if avg_len > 140.0 else 0.0
    len_pen = _clamp(short_pen + long_pen, 0.0, 1.0)

    base = 55.0
    score = base
    score += unique_ratio * 30.0
    score += title_presence_ratio * 10.0
    score -= (1.0 - unique_ratio) * 10.0
    score -= len_pen * 20.0

    score_i = int(round(_clamp(score, 0.0, 100.0)))

    metrics: dict[str, Any] = {
        "count": n,
        "unique_count": uniq,
        "unique_ratio": unique_ratio,
        "avg_len": avg_len,
        "title_presence_ratio": title_presence_ratio,
        "len_penalty": len_pen,
    }
    return CreativeQuality(score=score_i, metrics=metrics)
