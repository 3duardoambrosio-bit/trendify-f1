import re, sys
from pathlib import Path

TARGET_CALL = re.compile(r"\b(datetime|_dt)\.now_utc\(\)")

def compute_insert_at(lines):
    # after shebang / encoding / module docstring
    insert = 0
    if lines and lines[0].startswith("#!"):
        insert = 1
    enc = re.compile(r"coding[:=]\s*[-\w.]+")
    if len(lines) > insert and enc.search(lines[insert]):
        insert += 1

    # skip blank lines
    k = insert
    while k < len(lines) and lines[k].strip() == "":
        k += 1

    # docstring
    def starts_triple(s):
        s2 = s.lstrip()
        return s2.startswith('"""') or s2.startswith("'''")

    if k < len(lines) and starts_triple(lines[k]):
        q = '"""' if lines[k].lstrip().startswith('"""') else "'''"
        if lines[k].lstrip().count(q) >= 2:
            return k + 1
        j = k + 1
        while j < len(lines) and q not in lines[j]:
            j += 1
        return min(j + 1, len(lines))

    return k

def ensure_timezone_import(txt):
    # If already imported, we're good
    if re.search(r"(?m)^from datetime import .*?\btimezone\b", txt):
        return txt

    m = re.search(r"(?m)^from datetime import ([^\n]+)$", txt)
    if m:
        imports = m.group(1).strip()
        if re.search(r"\btimezone\b", imports):
            return txt
        new_line = f"from datetime import {imports}, timezone"
        return txt[:m.start()] + new_line + txt[m.end():]

    # fallback: insert standalone import near top
    lines = txt.splitlines()
    insert_at = compute_insert_at(lines)
    lines[insert_at:insert_at] = ["from datetime import timezone", ""]
    return "\n".join(lines) + "\n"

def patch_file(path: Path) -> bool:
    txt = path.read_text(encoding="utf-8")
    orig = txt

    if not TARGET_CALL.search(txt):
        return False

    txt = TARGET_CALL.sub(r"\1.now(timezone.utc)", txt)

    # we introduced timezone symbol -> ensure import exists
    txt = ensure_timezone_import(txt)

    if txt != orig:
        path.write_text(txt if txt.endswith("\n") else txt + "\n", encoding="utf-8")
        return True

    return False

def main(argv):
    if len(argv) < 2:
        print("Usage: fix_now_utc.py <file1> <file2> ...")
        return 2

    changed = 0
    for p in argv[1:]:
        path = Path(p)
        if not path.exists():
            print(f"MISS: {p}")
            continue
        if patch_file(path):
            print(f"OK: patched {p}")
            changed += 1
        else:
            print(f"SKIP: no now_utc in {p}")

    print(f"DONE: changed={changed}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
