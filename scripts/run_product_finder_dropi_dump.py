import json, os

def pick_list(raw):
    if isinstance(raw, dict):
        for k in ("objects", "data", "items", "products"):
            v = raw.get(k)
            if isinstance(v, list):
                return v
    if isinstance(raw, list):
        return raw
    raise RuntimeError("No encontré lista de productos en el dump (busqué objects/data/items/products).")

def to_decimal(x):
    try:
        return float(str(x).replace(",", "."))
    except Exception:
        return None

def score(p):
    cost = to_decimal(p.get("sale_price") or p.get("cost") or p.get("price_cost"))
    price = to_decimal(p.get("suggested_price") or p.get("price") or p.get("regular_price"))
    trust = to_decimal(p.get("trust_score") or p.get("provider_score") or p.get("supplier_score"))

    m_score = 0.0
    if cost is not None and price is not None and price > 0:
        m = (price - cost) / price
        m_score = max(0.0, min(1.0, m))

    imgs = p.get("gallery") or p.get("images") or []
    a_score = min(1.0, len(imgs) / 7.0) if isinstance(imgs, list) else 0.0

    t_score = max(0.0, min(1.0, trust / 10.0)) if trust is not None else 0.0

    s = 0.55*m_score + 0.25*a_score + 0.20*t_score
    return s, m_score, a_score, t_score

def main():
    dump_path = r"data\dropi_products_dump.json"
    if not os.path.exists(dump_path):
        print(f"No existe {dump_path}. Primero guarda ahí el JSON del Response de Dropi (/products/index).")
        return

    with open(dump_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    items = pick_list(raw)

    ranked = []
    for p in items:
        name = p.get("name") or p.get("title") or ""
        cat = ""
        cobj = p.get("category")
        if isinstance(cobj, dict):
            cat = cobj.get("name") or ""
        else:
            cat = p.get("category_name") or ""

        s, ms, a, t = score(p)
        ranked.append((s, name, cat, ms, a, t))

    ranked.sort(reverse=True, key=lambda x: x[0])

    print("TOP 5 (portal dump):")
    for i, (s, name, cat, ms, a, t) in enumerate(ranked[:5], 1):
        print(f"{i}. [{s:.4f}] {name} | {cat} | margin={ms:.2f} assets={a:.2f} trust={t:.2f}")

if __name__ == "__main__":
    main()
