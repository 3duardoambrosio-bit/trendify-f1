import argparse, csv, os, re, sys
from pathlib import Path

def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "item"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--canonical", required=True, help="canonical_products.csv (o patched)")
    ap.add_argument("--outdir", required=True, help="carpeta de salida para PNGs")
    ap.add_argument("--id-col", default="product_id")
    ap.add_argument("--title-col", default="title")
    ap.add_argument("--size", type=int, default=1200)
    args = ap.parse_args()

    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        print("Falta Pillow. Instala con:  pip install pillow", file=sys.stderr)
        return 2

    rows = list(csv.DictReader(open(args.canonical, encoding="utf-8", newline="")))
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    made = 0
    for r in rows:
        pid = str(r.get(args.id_col) or "").strip()
        title = str(r.get(args.title_col) or "").strip()
        if not pid:
            continue

        fn = f"{pid}.png"
        path = outdir / fn

        # imagen simple (blanca) con texto (negro)
        img = Image.new("RGB", (args.size, args.size), (255, 255, 255))
        draw = ImageDraw.Draw(img)

        # fuente default (evitamos depender de fonts del sistema)
        try:
            font_big = ImageFont.load_default()
            font_small = ImageFont.load_default()
        except Exception:
            font_big = font_small = None

        # texto
        t1 = pid
        t2 = title[:70] if title else "(sin título)"

        # centrado básico
        def center_text(text, y, font):
            w, h = draw.textbbox((0, 0), text, font=font)[2:]
            x = (args.size - w) // 2
            draw.text((x, y), text, fill=(0, 0, 0), font=font)

        center_text(t1, int(args.size * 0.45), font_big)
        center_text(t2, int(args.size * 0.52), font_small)

        img.save(path, format="PNG")
        made += 1

    print("generate_images: OK")
    print(f"- canonical: {args.canonical}")
    print(f"- outdir:    {outdir}")
    print(f"- made:      {made}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
