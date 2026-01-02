from __future__ import annotations

from synapse.marketing_os.creative_dedup import dedup_creatives, normalize_text, token_set, jaccard


def test_normalize_text_strips_accents_and_punct() -> None:
    assert normalize_text("Cámara!!! Pro") == "camara pro"


def test_jaccard_basic() -> None:
    a = token_set("hola mundo")
    b = token_set("hola mundo pro")
    assert 0.0 < jaccard(a, b) < 1.0


def test_dedup_creatives_drops_similar() -> None:
    creatives = [
        {"primary_text": "Producto X que sí cumple: mejor valor."},
        {"primary_text": "Producto X que si cumple mejor valor"},  # near-dup
        {"primary_text": "Upgrade inmediato: Producto X. mejor valor."},
    ]
    r = dedup_creatives(creatives, threshold=0.75)
    assert len(r.kept) == 2
    assert r.dropped == 1
