import argparse, csv, os, sys, zlib, struct, binascii

def _chunk(tag: bytes, data: bytes) -> bytes:
    crc = binascii.crc32(tag)
    crc = binascii.crc32(data, crc) & 0xffffffff
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

def write_png(path: str, w: int, h: int, rgb=(245,245,245)):
    # PNG RGB 8-bit, filter 0, zlib
    r,g,b = rgb
    raw = bytearray()
    row = bytes([0] + [r,g,b]*w)  # filter byte 0 + pixels
    for _ in range(h):
        raw += row

    comp = zlib.compress(bytes(raw), level=6)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)  # bitdepth=8 colortype=2(RGB)
    data = sig
    data += _chunk(b"IHDR", ihdr)
    data += _chunk(b"IDAT", comp)
    data += _chunk(b"IEND", b"")

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--canonical", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--id-col", default="product_id")
    ap.add_argument("--size", type=int, default=512)
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.canonical, encoding="utf-8", newline="")))
    if not rows:
        print("generate_blank_pngs: FAIL (canonical vacío)", file=sys.stderr)
        return 2

    outdir = args.outdir
    made = 0
    for r in rows:
        pid = str(r.get(args.id_col) or "").strip()
        if not pid:
            continue
        fp = os.path.join(outdir, f"{pid}.png")
        write_png(fp, args.size, args.size)
        made += 1

    print("generate_blank_pngs: OK")
    print(f"- canonical: {args.canonical}")
    print(f"- outdir:    {outdir}")
    print(f"- size:      {args.size}x{args.size}")
    print(f"- made:      {made}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
