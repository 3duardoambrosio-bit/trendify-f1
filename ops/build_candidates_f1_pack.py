from __future__ import annotations

import json, math, hashlib
from pathlib import Path
from datetime import datetime, timezone

from infra.ledger_v2 import LedgerV2
from synapse.quality_gate_v2 import QualityGateV2, QualityConfig

def clamp(x,a,b): return max(a, min(b, x))

def stable_seed(*parts):
    h = hashlib.sha256(("|".join([str(p) for p in parts])).encode("utf-8")).hexdigest()
    return int(h[:16], 16)

def lcg(seed):
    x = seed & 0xFFFFFFFFFFFFFFFF
    while True:
        x = (6364136223846793005 * x + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        yield x / 2**64

def quantiles(sorted_vals, qs):
    n = len(sorted_vals)
    out = []
    for q in qs:
        if n == 1:
            out.append(sorted_vals[0]); continue
        pos = q*(n-1)
        lo = int(math.floor(pos)); hi = int(math.ceil(pos))
        if lo == hi:
            out.append(sorted_vals[lo]); continue
        w = pos - lo
        out.append(sorted_vals[lo]*(1-w) + sorted_vals[hi]*w)
    return out

def confidence_heuristic(p):
    name = (p.get("name") or "").lower()
    score = float(p.get("score") or p.get("final_score") or p.get("s") or 0.5)
    margin = p.get("margin", None)
    imgs = int(p.get("imgs") or 0)

    f_imgs = 1.0 if imgs >= 3 else (0.7 if imgs >= 1 else 0.0)
    f_margin = 0.5
    if margin is not None:
        m = float(margin)
        f_margin = 1.0 if m >= 0.60 else (0.7 if m >= 0.45 else 0.2)
    f_score = 1.0 if score >= 0.66 else (0.7 if score >= 0.58 else 0.3)

    pen_oem = 1.0 if ("oem" in name) else 0.0
    pen_promo = 1.0 if ("promo" in name) else 0.0

    conf = 0.28 + 0.22*f_imgs + 0.28*f_margin + 0.20*f_score - 0.04*pen_oem - 0.03*pen_promo
    return clamp(conf, 0.20, 0.92), {
        "f_imgs": f_imgs,
        "f_margin": f_margin,
        "f_score": f_score,
        "pen_oem": pen_oem,
        "pen_promo": pen_promo
    }

def simulate_dist(mean, conf, seed):
    sigma = (1.0 - conf) * 0.18 + 0.03
    gen = lcg(seed)
    samples = []
    for _ in range(600):
        u1 = max(1e-12, next(gen)); u2 = next(gen)
        z = math.sqrt(-2.0*math.log(u1)) * math.cos(2*math.pi*u2)
        s = clamp(mean + z*sigma, 0.0, 1.0)
        samples.append(s)
    samples.sort()
    p10, p50, p90 = quantiles(samples, [0.10, 0.50, 0.90])
    return {"p10": p10, "p50": p50, "p90": p90, "sigma": sigma}

def recommend(p50, conf, risk):
    if risk >= 0.75 and conf >= 0.65: return "AVOID"
    if p50 >= 0.68 and conf >= 0.75: return "SCALE"
    if p50 >= 0.60 and conf < 0.75:  return "TEST"
    if p50 < 0.50 and conf >= 0.70:  return "SKIP"
    return "MONITOR"

def main():
    inp = Path(r"data\evidence\launch_candidates_dropi_dump.json")
    if not inp.exists():
        raise SystemExit(f"Missing: {inp}")

    j = json.loads(inp.read_text(encoding="utf-8"))
    arr = j.get("candidates") or j.get("top") or []
    if not isinstance(arr, list) or not arr:
        raise SystemExit("No candidates/top array found.")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # Config: ajustable; hoy lo dejamos conservador pero usable
    qcfg = QualityConfig(
        min_true_margin=0.35,
        fee_rate=0.04,
        return_rate=0.08,
        fixed_per_order=0.0,
        shipping_estimate=0.0,
        min_images=1
    )
    gate = QualityGateV2(qcfg)

    ledger = LedgerV2(Path(r"data\ledger"), max_bytes=5*1024*1024, batch_size=10)

    enriched = []
    drops = {"blocked": 0, "soft_unknown_margin": 0}
    for idx, p in enumerate(arr):
        mean = float(p.get("score") or p.get("final_score") or p.get("s") or 0.5)
        conf, feat = confidence_heuristic(p)

        seed = stable_seed(run_id, p.get("id",""), p.get("name",""), idx)
        dist = simulate_dist(mean, conf, seed)

        risk = float(p.get("risk") or 0.25)
        rec = recommend(dist["p50"], conf, risk)

        out = dict(p)
        out["confidence"] = conf
        out["confidence_breakdown"] = {"features": feat}
        out["score_dist"] = {"mean": mean, **dist}
        out["score_range"] = [dist["p10"], dist["p90"]]
        out["recommendation"] = rec
        out["psuccess"] = clamp(out.get("psuccess") or (dist["p50"]*0.95), 0.05, 0.92)

        # Quality Gate
        gres = gate.check(out)
        out["quality_gate"] = gate.explain(gres)

        ledger.write(
            event_type="candidate_scored",
            entity_type="product",
            entity_id=str(out.get("id") or out.get("name") or idx),
            trace_id=f"{run_id}_{idx}",
            payload={
                "name": out.get("name"),
                "score_p50": dist["p50"],
                "confidence": conf,
                "recommendation": rec,
                "gate_allowed": gres.allowed,
                "gate_blocks": [c.code for c in gres.blocks],
            }
        )

        if not gres.allowed:
            drops["blocked"] += 1
            continue
        if gres.true_margin is None:
            drops["soft_unknown_margin"] += 1

        enriched.append(out)

    ledger.write(
        event_type="decision_batch",
        entity_type="run",
        entity_id=run_id,
        trace_id=f"batch_{run_id}",
        payload={"source": str(inp), "count_in": len(arr), "count_out": len(enriched), "drops": drops}
    )
    ledger.close()

    outp = Path(r"data\evidence\launch_candidates_dropi_dump_f1_pack.json")
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps({
        "isSuccess": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "launch_candidates_dropi_dump.json",
        "top": enriched,
        "meta": {
            "engine": "F1_pack_v1",
            "count_in": len(arr),
            "count_out": len(enriched),
            "drops": drops,
            "quality_gate_config": {
                "min_true_margin": qcfg.min_true_margin,
                "fee_rate": qcfg.fee_rate,
                "return_rate": qcfg.return_rate,
                "min_images": qcfg.min_images
            }
        }
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    sample = enriched[0] if enriched else None
    print("OK pack:", outp)
    print("OK ledger:", r"data\ledger\ledger_*.ndjson")
    print("in:", len(arr), "out:", len(enriched), "drops:", drops)
    if sample:
        print("sample:", sample.get("name"), "conf=", round(sample["confidence"],2),
              "p50=", round(sample["score_dist"]["p50"],3),
              "range=", [round(x,3) for x in sample["score_range"]],
              "rec=", sample["recommendation"])

if __name__ == "__main__":
    main()
