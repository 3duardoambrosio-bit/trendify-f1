import json, math, pathlib, hashlib
from datetime import datetime

def clamp(x,a,b): return max(a, min(b, x))

def stable_seed(*parts):
    h = hashlib.sha256(("|".join([str(p) for p in parts])).encode("utf-8")).hexdigest()
    return int(h[:16], 16)

def lcg(seed):
    # deterministic pseudo-rng (no depende de random global)
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

def confidence_features(p):
    name = (p.get("name") or "").lower()
    score = float(p.get("score") or p.get("final_score") or p.get("s") or 0.5)
    margin = p.get("margin", None)
    imgs = int(p.get("imgs") or 0)

    # features (0..1-ish)
    f_imgs = 1.0 if imgs >= 3 else (0.7 if imgs >= 1 else 0.0)
    f_margin = 0.5
    if margin is not None:
        m = float(margin)
        f_margin = 1.0 if m >= 0.60 else (0.7 if m >= 0.45 else 0.2)
    f_score = 1.0 if score >= 0.66 else (0.7 if score >= 0.58 else 0.3)

    # soft penalties
    pen_oem = 1.0 if ("oem" in name) else 0.0
    pen_promo = 1.0 if ("promo" in name) else 0.0

    return {
        "f_imgs": f_imgs,
        "f_margin": f_margin,
        "f_score": f_score,
        "pen_oem": pen_oem,
        "pen_promo": pen_promo
    }

def confidence_from_features(feat):
    # weighted, bounded; easy to tune later
    base = 0.28
    w = (
        base
        + 0.22*feat["f_imgs"]
        + 0.28*feat["f_margin"]
        + 0.20*feat["f_score"]
        - 0.04*feat["pen_oem"]
        - 0.03*feat["pen_promo"]
    )
    return clamp(w, 0.20, 0.92)

def simulate_score_distribution(mean, conf, seed):
    # convert confidence to sigma
    sigma = (1.0 - conf) * 0.18 + 0.03
    gen = lcg(seed)
    samples = []
    # Box-Muller with deterministic uniforms
    for _ in range(600):
        u1 = max(1e-12, next(gen))
        u2 = next(gen)
        z = math.sqrt(-2.0*math.log(u1)) * math.cos(2*math.pi*u2)
        s = clamp(mean + z*sigma, 0.0, 1.0)
        samples.append(s)
    samples.sort()
    p10, p50, p90 = quantiles(samples, [0.10, 0.50, 0.90])
    return {"p10": p10, "p50": p50, "p90": p90, "sigma": sigma}

def recommend(score_p50, conf, risk):
    # policy simple pero seria: depende de confianza
    if risk >= 0.75 and conf >= 0.65: return "AVOID"
    if score_p50 >= 0.68 and conf >= 0.75: return "SCALE"
    if score_p50 >= 0.60 and conf < 0.75:  return "TEST"
    if score_p50 < 0.50 and conf >= 0.70:  return "SKIP"
    return "MONITOR"

def normalize_prices(p):
    sp = p.get("suggested_price", None)
    if sp is None: sp = p.get("sp", None)
    cost = p.get("sale_price", None)
    if cost is None: cost = p.get("cost", None)

    if sp is not None and cost is None and p.get("margin") is not None:
        try:
            spv = float(sp); mv = float(p["margin"])
            cost = round(spv * (1.0 - mv))
        except:
            pass
    return sp, cost

def ensure_dir(path):
    path.parent.mkdir(parents=True, exist_ok=True)

def append_ndjson(path, obj):
    ensure_dir(path)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def enrich_item(p, idx, run_id):
    mean = float(p.get("score") or p.get("final_score") or p.get("s") or 0.5)
    feat = confidence_features(p)
    conf = float(p.get("confidence") or p.get("conf") or confidence_from_features(feat))

    seed = stable_seed(run_id, p.get("id",""), p.get("name",""), idx)
    dist = simulate_score_distribution(mean, conf, seed)

    risk = float(p.get("risk") or 0.25)
    rec = recommend(dist["p50"], conf, risk)

    sp, cost = normalize_prices(p)
    margin = p.get("margin", None)
    if margin is None and sp and cost:
        try:
            spv=float(sp); cv=float(cost)
            margin = (spv-cv)/spv if spv>0 else None
        except:
            pass

    out = dict(p)
    out["id"] = out.get("id") or f"cand_{idx}"
    out["confidence"] = conf
    out["confidence_breakdown"] = {
        "features": feat,
        "notes": [
            "Confidence = weighted evidence quality (imgs/margin/score) minus soft penalties",
            "Tunable weights; deterministic per input"
        ]
    }
    out["score_dist"] = {
        "mean": mean,
        "p10": dist["p10"],
        "p50": dist["p50"],
        "p90": dist["p90"],
        "sigma": dist["sigma"]
    }
    out["score_range"] = [dist["p10"], dist["p90"]]
    out["recommendation"] = rec

    if sp is not None: out["suggested_price"] = sp
    if cost is not None: out["sale_price"] = cost
    if margin is not None: out["margin"] = float(margin)

    # psuccess: por ahora ligado a p50, luego se calibra con outcomes
    out["psuccess"] = clamp(out.get("psuccess") or (dist["p50"]*0.95), 0.05, 0.92)
    return out

def main():
    inp = pathlib.Path(r"data\evidence\launch_candidates_dropi_dump.json")
    if not inp.exists():
        raise SystemExit(f"Missing: {inp}")

    j = json.loads(inp.read_text(encoding="utf-8"))
    arr = j.get("candidates") or j.get("top") or []
    if not isinstance(arr, list) or not arr:
        raise SystemExit("No candidates/top array found in JSON.")

    run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    enriched = [enrich_item(p, i, run_id) for i,p in enumerate(arr)]

    out = {
        "isSuccess": True,
        "source": "launch_candidates_dropi_dump.json",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "top": enriched,
        "meta": {
            "count": len(enriched),
            "engine": "F1_enrich_v2",
            "notes": [
                "Adds confidence_breakdown + score_dist(p10/p50/p90) + recommendation",
                "Writes NDJSON audit event for reconstruction"
            ]
        }
    }

    outp = pathlib.Path(r"data\evidence\launch_candidates_dropi_dump_f1_v2.json")
    outp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    audit_path = pathlib.Path(r"data\ledger\decision_audit.ndjson")
    audit_event = {
        "type": "decision_batch",
        "ts": datetime.utcnow().isoformat() + "Z",
        "run_id": run_id,
        "source_file": str(inp),
        "out_file": str(outp),
        "count": len(enriched),
        "policy": {
            "recommendation_rules": ["SCALE/TEST/MONITOR/SKIP/AVOID based on p50 + confidence + risk"],
            "confidence_model": "weighted evidence quality"
        }
    }
    append_ndjson(audit_path, audit_event)

    print("OK F1 v2:", outp)
    print("OK audit ndjson:", audit_path)
    s = enriched[0]
    print("sample:", s["name"], "conf=", round(s["confidence"],2), "p50=", round(s["score_dist"]["p50"],3), "range=", [round(x,3) for x in s["score_range"]], "rec=", s["recommendation"])

if __name__ == "__main__":
    main()
