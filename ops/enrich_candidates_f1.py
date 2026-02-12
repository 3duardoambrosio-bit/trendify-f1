from synapse.infra.cli_logging import cli_print

import json, math, pathlib, random
from datetime import datetime, timezone
def clamp(x,a,b): return max(a, min(b, x))

def confidence_heuristic(p):
    # Señales que sí tenemos hoy
    score = float(p.get("score") or p.get("final_score") or p.get("s") or 0.5)
    margin = p.get("margin", None)
    imgs = int(p.get("imgs") or 0)

    c = 0.45
    c += 0.10 if imgs >= 1 else -0.20
    c += 0.08 if imgs >= 3 else 0.00
    if margin is not None:
        m = float(margin)
        c += 0.18 if m >= 0.60 else (0.10 if m >= 0.45 else -0.10)
    c += 0.10 if score >= 0.62 else (0.00 if score >= 0.55 else -0.08)

    # Penaliza nombres raros (ruido / dupe / OEM) — suave, no bloquea
    name = (p.get("name") or "").lower()
    if "oem" in name or "promo" in name: c -= 0.04

    return clamp(c, 0.20, 0.92)

def score_range(score, conf):
    # Delta baja cuando sube confianza
    delta = (1.0 - conf) * 0.22 + 0.03
    lo = clamp(score - delta, 0.0, 1.0)
    hi = clamp(score + delta, 0.0, 1.0)
    return (lo, hi, delta)

def recommend(score, conf, risk=0.25):
    # risk placeholder: cuando tengamos risk real, esto se vuelve quirúrgico
    if risk >= 0.75 and conf >= 0.65: return "AVOID"
    if score >= 0.66 and conf >= 0.72: return "SCALE"
    if score >= 0.60 and conf < 0.72:  return "TEST"
    if score < 0.52 and conf >= 0.70:  return "SKIP"
    return "MONITOR"

def infer_prices(p):
    # Mantén compatibilidad: UI ahorita entiende suggested_price y sale_price
    sp = p.get("suggested_price", None)
    if sp is None: sp = p.get("sp", None)
    cost = p.get("sale_price", None)
    if cost is None: cost = p.get("cost", None)
    if sp is not None and cost is None and p.get("margin") is not None:
        try:
            spv = float(sp); mv = float(p["margin"])
            cost = round(spv * (1.0 - mv))
        except: pass
    return sp, cost

def enrich_item(p, idx):
    score = float(p.get("score") or p.get("final_score") or p.get("s") or 0.5)
    conf = float(p.get("confidence") or p.get("conf") or confidence_heuristic(p))
    lo, hi, delta = score_range(score, conf)

    sp, cost = infer_prices(p)
    psuccess = p.get("psuccess", None)
    if psuccess is None:
        psuccess = clamp(score * 0.95, 0.05, 0.92)

    out = dict(p)
    out["id"] = out.get("id") or f"cand_{idx}"
    out["confidence"] = conf
    out["score_range"] = [lo, hi]
    out["score_delta"] = delta
    out["psuccess"] = psuccess
    out["recommendation"] = recommend(score, conf, risk=float(out.get("risk", 0.25) or 0.25))

    # Normaliza nombres de precio para UI
    if sp is not None: out["suggested_price"] = sp
    if cost is not None: out["sale_price"] = cost
    return out

def main():
    inp = pathlib.Path(r"data\evidence\launch_candidates_dropi_dump.json")
    if not inp.exists():
        raise SystemExit(f"Missing: {inp}")

    j = json.loads(inp.read_text(encoding="utf-8"))
    arr = j.get("candidates") or j.get("top") or []
    if not isinstance(arr, list) or not arr:
        raise SystemExit("No candidates/top array found in JSON.")

    enriched = [enrich_item(p, i) for i,p in enumerate(arr)]
    out = {
        "isSuccess": True,
        "source": "launch_candidates_dropi_dump.json",
        "generated_at": datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
        "top": enriched,
        "meta": {
            "count": len(enriched),
            "notes": [
                "F1 enrichment: adds confidence, score_range, psuccess, recommendation",
                "Prices normalized to suggested_price + sale_price when possible"
            ]
        }
    }

    outp = pathlib.Path(r"data\evidence\launch_candidates_dropi_dump_f1.json")
    outp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    cli_print("OK F1 candidates:", outp)
    cli_print("sample:", enriched[0]["name"], "conf=", round(enriched[0]["confidence"],2), "range=", enriched[0]["score_range"], "rec=", enriched[0]["recommendation"])

if __name__ == "__main__":
    main()
