import re, sys
from pathlib import Path

path = Path(sys.argv[1])
txt = path.read_text(encoding="utf-8")
lines = txt.splitlines()

target = "from __future__ import annotations"
idxs = [i for i,l in enumerate(lines) if l.strip() == target]
if not idxs:
    print(f"SKIP: no future import in {path}")
    raise SystemExit(0)

# remove all occurrences
lines = [l for l in lines if l.strip() != target]

# detect insertion point: after shebang/encoding/docstring (if any)
insert = 0
if lines and lines[0].startswith("#!"):
    insert = 1

enc_re = re.compile(r"coding[:=]\s*[-\w.]+")
if len(lines) > insert and enc_re.search(lines[insert]):
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
    # single-line docstring?
    if lines[k].lstrip().count(q) >= 2:
        insert = k + 1
    else:
        j = k + 1
        while j < len(lines) and q not in lines[j]:
            j += 1
        insert = min(j + 1, len(lines))
else:
    insert = k

# insert future import + blank line
lines[insert:insert] = [target, ""]

path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"OK: moved future import to top region in {path}")
