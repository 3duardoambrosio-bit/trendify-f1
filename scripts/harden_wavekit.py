import argparse, hashlib, json, os, sys, zipfile
from pathlib import Path

TEXT_EXTS = {".json", ".ndjson", ".csv", ".txt", ".md"}

REQ = {
    "bundle.zip",
    "creatives.ndjson",
    "manifest.json",
    "meta/meta_assets.json",
    "quality.json",
    "shopify/shopify_products.csv",
}

def sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def posix_rel(rel: str) -> str:
    return (rel or "").replace("\\", "/").replace("//", "/")

def normalize_bytes(b: bytes) -> tuple[bytes, bool, bool]:
    """Return (new_bytes, bom_stripped, eol_normalized)"""
    bom = b"\xef\xbb\xbf"
    bom_stripped = False
    if b.startswith(bom):
        b = b[len(bom):]
        bom_stripped = True

    # Normalize line endings to LF
    eol_normalized = False
    if b"\r\n" in b or b"\r" in b:
        b = b.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        eol_normalized = True
    return b, bom_stripped, eol_normalized

def normalize_text_file(p: Path) -> dict:
    b0 = p.read_bytes()
    b1, bom_stripped, eol_norm = normalize_bytes(b0)
    changed = (b1 != b0)
    if changed:
        p.write_bytes(b1)
    return {
        "path": str(p),
        "changed": changed,
        "bom_stripped": bom_stripped,
        "eol_norm": eol_norm,
        "bytes_before": len(b0),
        "bytes_after": len(b1),
    }

def rebuild_bundle_zip(kit_dir: Path, bundle_rel: str = "bundle.zip") -> dict:
    bundle_path = kit_dir / bundle_rel
    if not bundle_path.exists():
        raise FileNotFoundError(f"bundle.zip no existe: {bundle_path}")

    # bundle.zip should contain the 4 canonical files
    want = ["creatives.ndjson", "quality.json", "meta/meta_assets.json", "shopify/shopify_products.csv"]
    tmp = bundle_path.with_suffix(".zip.tmp")

    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for rel in want:
            src = kit_dir / Path(rel)
            if not src.exists():
                raise FileNotFoundError(f"Falta archivo para bundle.zip: {src}")
            data = src.read_bytes()
            zout.writestr(rel, data)

    tmp.replace(bundle_path)
    return {"bundle_path": str(bundle_path), "rebuilt": True, "files": want}

def compute_self_hash(manifest: dict) -> str:
    # Stable JSON hash (common pattern)
    b = json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(b)

def load_manifest(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))

def save_manifest(p: Path, m: dict) -> None:
    p.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def update_manifest_hashes(kit_dir: Path, manifest: dict) -> dict:
    artifacts = manifest.get("artifacts", [])
    new_artifacts = []
    for a in artifacts:
        rel0 = a.get("relpath", "")
        rel = posix_rel(rel0)
        fp = kit_dir / Path(rel.replace("/", os.sep))
        if not fp.exists():
            raise FileNotFoundError(f"Artifact en manifest no existe en kit_dir: relpath={rel} path={fp}")
        b = fp.read_bytes()
        new_artifacts.append({
            "bytes": len(b),
            "relpath": rel,
            "sha256": sha256_bytes(b),
        })
    manifest["artifacts"] = new_artifacts

    # self_hash should ignore itself
    tmp = dict(manifest)
    tmp.pop("self_hash", None)
    manifest["self_hash"] = compute_self_hash(tmp)
    return manifest

def build_release_zip(kit_dir: Path, out_zip: Path) -> dict:
    files = [p for p in kit_dir.rglob("*") if p.is_file()]
    files.sort(key=lambda p: str(p).lower())
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in files:
            rel = p.relative_to(kit_dir).as_posix()
            z.write(p, rel)
    return {"out_zip": str(out_zip), "files": len(files), "sha256": sha256_file(out_zip)}

def write_sha_sidecar(out_zip: Path, sha_hex: str) -> Path:
    side = out_zip.with_suffix(".sha256")
    side.write_text(f"{sha_hex}  {out_zip.name}\n", encoding="utf-8")
    return side

def validate_wavekit_zip(zip_path: Path) -> dict:
    with zipfile.ZipFile(zip_path) as z:
        names = set(z.namelist())
        miss = REQ - names
        if miss:
            raise AssertionError(f"MISSING in wavekit zip: {sorted(miss)}")

        m = json.loads(z.read("manifest.json").decode("utf-8"))

        # Validate artifact hashes vs zip contents
        for a in m.get("artifacts", []):
            rel = posix_rel(a.get("relpath", ""))
            if rel not in names:
                raise AssertionError(f"MANIFEST relpath not in zip: {rel}")
            got = sha256_bytes(z.read(rel))
            exp = a.get("sha256")
            if exp and got != exp:
                raise AssertionError(f"SHA_MISMATCH {rel}: got={got} exp={exp}")

        # Validate bundle.zip contains canonical 4
        with zipfile.ZipFile(z.open("bundle.zip")) as bz:
            bnames = set(bz.namelist())
            bneed = {"creatives.ndjson", "quality.json", "meta/meta_assets.json", "shopify/shopify_products.csv"}
            bmiss = bneed - bnames
            if bmiss:
                raise AssertionError(f"MISSING in bundle.zip: {sorted(bmiss)}")

        # CSV checks: no BOM, LF only
        csvb = z.read("shopify/shopify_products.csv")
        if csvb.startswith(b"\xef\xbb\xbf"):
            raise AssertionError("CSV_HAS_BOM")
        if b"\r\n" in csvb or b"\r" in csvb:
            raise AssertionError("CSV_HAS_CRLF (want LF)")
        csvb.decode("utf-8")

    return {"zip_ok": True, "required_ok": True}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kit_dir", help="e.g. exports\\seed or exports\\p1")
    ap.add_argument("--out-zip", default="", help="Optional output zip path. Default: exports\\wave_kit_<product_id>.zip")
    args = ap.parse_args()

    kit_dir = Path(args.kit_dir).resolve()
    if not kit_dir.is_dir():
        raise SystemExit(f"kit_dir no existe: {kit_dir}")

    manifest_path = kit_dir / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"manifest.json no existe en kit_dir: {manifest_path}")

    # 1) Normalize text artifacts on disk (including manifest itself)
    changed = []
    for p in kit_dir.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() in TEXT_EXTS or p.name == "manifest.json":
            changed.append(normalize_text_file(p))

    normalized_files = sum(1 for x in changed if x["changed"])

    # 2) Force POSIX relpaths in manifest + rebuild hashes + self_hash
    manifest = load_manifest(manifest_path)
    pid = manifest.get("product_id", "wavekit")
    for a in manifest.get("artifacts", []):
        a["relpath"] = posix_rel(a.get("relpath", ""))

    # 3) Rebuild bundle.zip from normalized disk versions
    bund = rebuild_bundle_zip(kit_dir)

    # 4) Update manifest hashes AFTER bundle rebuild
    manifest = update_manifest_hashes(kit_dir, manifest)
    save_manifest(manifest_path, manifest)

    # 5) Decide output zip path
    if args.out_zip.strip():
        out_zip = Path(args.out_zip).resolve()
    else:
        out_zip = (kit_dir.parent / f"wave_kit_{pid}.zip").resolve()

    # 6) Build release zip + sha sidecar
    built = build_release_zip(kit_dir, out_zip)
    side = write_sha_sidecar(out_zip, built["sha256"])

    # 7) Validate the release zip
    val = validate_wavekit_zip(out_zip)

    # Human output
    print("PASS: harden_wavekit OK")
    print(f"- kit_dir: {kit_dir}")
    print(f"- product_id: {pid}")
    print(f"- out_zip: {out_zip}")
    print(f"- sha256: {built['sha256']}")
    print(f"- sidecar: {side}")
    print(f"- normalized_files: {normalized_files} changed (of {len(changed)})")
    print(f"- bundle_rebuilt: {bund.get('rebuilt', False)}")
    print(f"- validate: {val}")

    # Machine-readable output for gates
    summary = {
        "kit_dir": str(kit_dir),
        "product_id": str(pid),
        "out_zip": str(out_zip),
        "sha256": str(built["sha256"]),
        "sidecar": str(side),
        "normalized_files": int(normalized_files),
        "normalized_total": int(len(changed)),
        "bundle_rebuilt": bool(bund.get("rebuilt", False)),
        "validate": val,
    }
    print("HARDEN_SUMMARY_JSON=" + json.dumps(summary, ensure_ascii=False, separators=(",", ":")))

if __name__ == "__main__":
    main()
