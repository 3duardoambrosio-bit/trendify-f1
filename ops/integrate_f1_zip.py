from synapse.infra.cli_logging import cli_print

import argparse, re, zipfile, shutil
from pathlib import Path
from datetime import datetime

MARKER_RE = re.compile(r"^#\s+([\w\-/\\\.]+\.py)\s*$")

def now_tag():
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def backup_if_exists(path: Path):
    if path.exists():
        bak = path.with_suffix(path.suffix + f".bak_{now_tag()}")
        bak.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, bak)

def split_marked_py(text: str):
    lines = text.splitlines(keepends=True)
    hits = [(i, MARKER_RE.match(lines[i]).group(1)) for i in range(len(lines)) if MARKER_RE.match(lines[i])]
    if not hits:
        raise SystemExit("No encontré marcadores '# ruta/archivo.py' en el archivo de código. ZIP raro.")
    for idx, (i, rel) in enumerate(hits):
        start = i + 1
        end = hits[idx + 1][0] if idx + 1 < len(hits) else len(lines)
        body = "".join(lines[start:end])
        # quita puro espacio inicial para que no se guarde con líneas vacías al inicio
        body = body.lstrip("\n")
        yield rel.strip(), body

def sanitize_rel(rel: str) -> Path:
    rel = rel.replace("\\", "/").strip()
    if rel.startswith("/") or rel.startswith(".."):
        raise SystemExit(f"Ruta sospechosa en ZIP: {rel}")
    return Path(rel)

def ensure_init_py(repo: Path, pkg_dir: Path):
    initp = repo / pkg_dir / "__init__.py"
    if not initp.exists():
        initp.parent.mkdir(parents=True, exist_ok=True)
        initp.write_text("# auto-created for package\n", encoding="utf-8")

def write_files(repo: Path, items, label: str):
    written = []
    for rel, body in items:
        out_rel = sanitize_rel(rel)
        out_path = repo / out_rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        backup_if_exists(out_path)
        out_path.write_text(body.rstrip() + "\n", encoding="utf-8")
        written.append(out_rel.as_posix())
    cli_print(f"OK {label}: {len(written)} archivos")
    return written

def parse_data_files(text: str):
    # Formato: bloques con "FILE: path"
    parts = re.split(r"^FILE:\s+(.+)$", text, flags=re.M)
    # parts[0]=preambulo, luego (fname, content)...
    items = []
    for i in range(1, len(parts), 2):
        fname = parts[i].strip()
        content = parts[i+1]
        # limpia separadores "=====" al inicio/fin (porque si no, contaminaría listas)
        lines = content.splitlines()
        # drop leading blanks / ==== lines
        while lines and (not lines[0].strip() or set(lines[0].strip()) == {"="}):
            lines.pop(0)
        # drop trailing ==== lines
        while lines and (not lines[-1].strip() or set(lines[-1].strip()) == {"="}):
            lines.pop()
        cleaned = "\n".join(lines).rstrip() + "\n"
        items.append((fname, cleaned))
    if not items:
        raise SystemExit("No pude parsear DATA_FILES.txt (no hallé 'FILE:').")
    return items

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True, help="Ruta al ZIP (ej: .\\sssdasdasd.zip)")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]  # ops/.. = repo root
    zpath = Path(args.zip).resolve()
    if not zpath.exists():
        raise SystemExit(f"No existe el zip: {zpath}")

    with zipfile.ZipFile(zpath, "r") as z:
        need = ["SYNAPSE_F1_CODIGO_COMPLETO.py", "SYNAPSE_F1_TESTS_COMPLETOS.py", "SYNAPSE_F1_DATA_FILES.txt"]
        for n in need:
            if n not in z.namelist():
                raise SystemExit(f"ZIP no trae {n}. Trae: {z.namelist()}")

        code = z.read("SYNAPSE_F1_CODIGO_COMPLETO.py").decode("utf-8", errors="strict")
        tests = z.read("SYNAPSE_F1_TESTS_COMPLETOS.py").decode("utf-8", errors="strict")
        data = z.read("SYNAPSE_F1_DATA_FILES.txt").decode("utf-8", errors="strict")

    code_items = list(split_marked_py(code))
    test_items = list(split_marked_py(tests))
    data_items = parse_data_files(data)

    # Asegura paquetes básicos (por si faltan __init__.py)
    for pkg in ["synapse", "core", "infra", "vault", "ops", "tests", "synapse/data"]:
        ensure_init_py(repo, Path(pkg))

    written_code = write_files(repo, code_items, "code")
    written_tests = write_files(repo, test_items, "tests")
    written_data = write_files(repo, data_items, "data")

    cli_print("\nResumen:")
    cli_print(" - code:", len(written_code))
    cli_print(" - tests:", len(written_tests))
    cli_print(" - data:", len(written_data))
    cli_print("\nSiguiente: instala deps y corre pytest.")

if __name__ == "__main__":
    main()
