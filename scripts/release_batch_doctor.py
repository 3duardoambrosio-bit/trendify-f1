import argparse, csv, json, os, sys, re
from pathlib import Path
from datetime import datetime

PLACEHOLDER_RE = re.compile(r"(via\.placeholder\.com|dummyimage\.com|placehold\.it|picsum\.photos)", re.I)

def read_text(path: Path, enc: str):
    return path.read_text(encoding=enc)

def load_json_any(path: Path):
    # index.json suele venir con BOM; probamos utf-8-sig primero
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return json.loads(read_text(path, enc))
        except Exception:
            pass
    raise ValueError(f"JSON decode failed for {path}")

def is_placeholder(u: str) -> bool:
    if not u:
        return False
    return bool(PLACEHOLDER_RE.search(u.strip()))

def csv_rows(path: Path):
    # canonical suele estar utf-8; otros pueden venir con BOM
    for enc in ("utf-8", "utf-8-sig"):
        try:
            with path.open("r", encoding=enc, newline="") as f:
                return list(csv.DictReader(f))
        except Exception:
            continue
    raise ValueError(f"CSV read failed for {path}")

def pick_latest_batch_dir(root: Path) -> Path | None:
    if not root.exists():
        return None
    dirs = [p for p in root.iterdir() if p.is_dir()]
    if not dirs:
        return None
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return dirs[0]

def pct(n, d):
    return 0.0 if d == 0 else (n / d)

def doctor(batch_dir: Path, mode: str, allow_placeholders: bool):
    # Files we expect (based on your pipeline)
    canonical = batch_dir / "canonical_products.csv"
    canonical_patched = batch_dir / "canonical_products.patched.csv"
    index_json = batch_dir / "index.json"

    shopify_all = batch_dir / "shopify_import_all.csv"
    shopify_all_patched = batch_dir / "shopify_import_all.patched.csv"
    shopify_report = Path(str(shopify_all_patched) + ".contract_report.json")
    shopify_clean = Path(str(shopify_all_patched) + ".contract_report.clean.json")

    status = {"errors": [], "warnings": [], "facts": []}

    def ERR(msg): status["errors"].append(msg)
    def WARN(msg): status["warnings"].append(msg)
    def FACT(msg): status["facts"].append(msg)

    # 0) Batch dir exists
    if not batch_dir.exists():
        ERR(f"Batch dir no existe: {batch_dir}")
        return status

    FACT(f"batch_dir={batch_dir}")

    # 1) Index integrity
    if not index_json.exists():
        ERR(f"Falta index.json: {index_json}")
    else:
        idx = load_json_any(index_json)
        if not isinstance(idx, list):
            ERR("index.json no es lista")
        else:
            missing = []
            for it in idx:
                if not isinstance(it, dict):
                    continue
                pid = it.get("product_id", "(unknown)")
                for k in ("zip", "sha256", "meta"):
                    fp = it.get(k)
                    if fp and not Path(fp).exists():
                        missing.append((pid, k, fp))
            if missing:
                ERR(f"index.json referencias rotas: {len(missing)} (sample={missing[:5]})")
            else:
                FACT(f"index.json OK: items={len(idx)} (zip/sha/meta existen)")

    # 2) Canonical stats
    if not canonical.exists():
        ERR(f"Falta canonical_products.csv: {canonical}")
    else:
        rows = csv_rows(canonical)
        FACT(f"canonical_rows={len(rows)}")

    if canonical_patched.exists():
        rows_p = csv_rows(canonical_patched)
        total = len(rows_p)
        img_http = sum(1 for r in rows_p if (r.get("image_url") or "").strip().startswith("http"))
        img_placeholder = sum(1 for r in rows_p if is_placeholder((r.get("image_url") or "").strip()))
        FACT(f"canonical_patched_rows={total}")
        FACT(f"canonical_patched_image_http={img_http} ({pct(img_http,total):.3f})")
        FACT(f"canonical_patched_placeholders={img_placeholder} ({pct(img_placeholder,total):.3f})")

        if mode == "prod":
            if img_http == 0:
                ERR("PROD: canonical_patched no tiene image_url http")
            if img_placeholder > 0:
                ERR("PROD: canonical_patched tiene placeholders (prohibido)")
        else:
            # demo/bootstrap
            if img_http == 0:
                WARN("DEMO: canonical_patched no tiene image_url http")
            if img_placeholder > 0 and not allow_placeholders:
                WARN("DEMO: hay placeholders pero allow_placeholders=False")
    else:
        WARN(f"Falta canonical_products.patched.csv (aún no parcheado): {canonical_patched}")

    # 3) Shopify import CSV stats
    if not shopify_all.exists():
        WARN(f"Falta shopify_import_all.csv (merge aún no corrido): {shopify_all}")
    else:
        FACT(f"shopify_import_all.csv existe")

    if not shopify_all_patched.exists():
        WARN(f"Falta shopify_import_all.patched.csv (aún no parcheado): {shopify_all_patched}")
    else:
        srows = csv_rows(shopify_all_patched)
        total = len(srows)
        img_http = sum(1 for r in srows if (r.get("Image Src") or "").strip().startswith("http"))
        img_placeholder = sum(1 for r in srows if is_placeholder((r.get("Image Src") or "").strip()))
        FACT(f"shopify_patched_rows={total}")
        FACT(f"shopify_patched_image_http={img_http} ({pct(img_http,total):.3f})")
        FACT(f"shopify_patched_placeholders={img_placeholder} ({pct(img_placeholder,total):.3f})")

        if mode == "prod":
            if img_http == 0:
                ERR("PROD: shopify_import_all.patched.csv no tiene Image Src http")
            if img_placeholder > 0:
                ERR("PROD: shopify_import_all.patched.csv tiene placeholders (prohibido)")
        else:
            if img_http == 0:
                WARN("DEMO: shopify_import_all.patched.csv no tiene Image Src http")
            if img_placeholder > 0 and not allow_placeholders:
                WARN("DEMO: hay placeholders pero allow_placeholders=False")

    # 4) Contract gate reports
    if shopify_clean.exists():
        rep = load_json_any(shopify_clean)
        errs = rep.get("errors", [])
        warns = rep.get("warnings", [])
        FACT(f"contract_gate_clean: errors={len(errs)} warnings={len(warns)} (ignored={len(rep.get('warnings_ignored',[]))})")
        if errs:
            ERR(f"contract_gate_clean tiene errors: sample={errs[:2]}")
        if warns:
            WARN(f"contract_gate_clean tiene warnings: sample={warns[:2]}")
    elif shopify_report.exists():
        rep = load_json_any(shopify_report)
        errs = rep.get("errors", [])
        warns = rep.get("warnings", [])
        FACT(f"contract_gate: errors={len(errs)} warnings={len(warns)}")
        if errs:
            ERR(f"contract_gate tiene errors: sample={errs[:2]}")
        else:
            # en demo, warnings pueden ser ruido si son placeholders allowed
            if mode == "prod" and warns:
                WARN(f"PROD: contract_gate warnings: sample={warns[:2]}")
            if mode != "prod":
                WARN(f"DEMO: contract_gate warnings (normal si placeholders): sample={warns[:2]}")
    else:
        WARN("No encontré contract report (ni .contract_report.json ni .clean.json).")

    return status

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-dir", default="", help="Ruta a exports/releases/_batch/<batch_id>")
    ap.add_argument("--auto-latest", action="store_true", help="Auto-detect latest batch dir in exports/releases/_batch")
    ap.add_argument("--mode", choices=["demo", "prod"], default="demo")
    ap.add_argument("--allow-placeholders", action="store_true")
    args = ap.parse_args()

    batch_dir = Path(args.batch_dir) if args.batch_dir else None
    if args.auto_latest:
        batch_dir = pick_latest_batch_dir(Path("exports") / "releases" / "_batch")

    if not batch_dir:
        print("release_batch_doctor: FAIL (no batch_dir). Usa --batch-dir o --auto-latest.", file=sys.stderr)
        return 2

    status = doctor(batch_dir, mode=args.mode, allow_placeholders=args.allow_placeholders)

    print("============================================================")
    print("RELEASE BATCH DOCTOR")
    print("============================================================")
    print(f"timestamp: {datetime.utcnow().isoformat()}Z")
    print(f"mode: {args.mode}")
    print(f"allow_placeholders: {args.allow_placeholders}")
    print("")

    for f in status["facts"]:
        print("✓", f)
    if status["warnings"]:
        print("")
        for w in status["warnings"]:
            print("⚠", w)
    if status["errors"]:
        print("")
        for e in status["errors"]:
            print("✗", e)

    print("")
    if status["errors"]:
        print("RESULT: FAIL")
        return 1
    if status["warnings"]:
        print("RESULT: WARN")
        return 0
    print("RESULT: OK")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
