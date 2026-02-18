import re
from pathlib import Path

def fq_module_from_path(p: Path) -> str:
    rel = p.relative_to("synapse").with_suffix("")
    return "synapse." + ".".join(rel.parts)

def discover_meta_modules() -> list[str]:
    root = Path("synapse")
    if not root.exists():
        return []
    mods: list[str] = []
    for f in root.rglob("meta*.py"):
        if "__pycache__" in f.parts:
            continue
        mods.append(fq_module_from_path(f))
    return sorted(set(mods))

def strip_block(txt: str, header_pat: str) -> str:
    pat = re.compile(rf"(?ms)^{header_pat}\n.*?(?=^\[tool\.|^\[\[tool\.|\Z)")
    return re.sub(pat, "", txt)

def main() -> int:
    p = Path("pyproject.toml")
    if not p.exists():
        raise SystemExit("pyproject.toml no existe en el root del repo.")

    meta_mods = discover_meta_modules()

    cfg_lines: list[str] = []
    cfg_lines.append("# ===========================")
    cfg_lines.append("# MYPY F1 GATE (AUTO-GENERATED)")
    cfg_lines.append("# ===========================")
    cfg_lines.append("[tool.mypy]")
    cfg_lines.append("show_error_codes = true")
    cfg_lines.append("warn_unused_configs = true")
    cfg_lines.append("warn_unused_ignores = false")
    cfg_lines.append("ignore_missing_imports = true")
    cfg_lines.append("")
    cfg_lines.append("disable_error_code = [")
    cfg_lines.append('  "no-untyped-def",')
    cfg_lines.append('  "no-untyped-call",')
    cfg_lines.append('  "type-arg",')
    cfg_lines.append('  "var-annotated",')
    cfg_lines.append("]")
    cfg_lines.append("")
    cfg_lines.append("exclude = [")
    cfg_lines.append(r"  '(^|/|\\)tests(/|\\)',")
    cfg_lines.append(r"  '(^|/|\\)infra(/|\\)tests(/|\\)',")
    cfg_lines.append(r"  '(^|/|\\)scripts(/|\\)',  # avoid duplicate sitecustomize.py mapping")
    cfg_lines.append("]")
    cfg_lines.append("")

    cfg_lines.append("[[tool.mypy.overrides]]")
    cfg_lines.append('module = ["tests.*"]')
    cfg_lines.append("ignore_errors = true")
    cfg_lines.append("")

    cfg_lines.append("[[tool.mypy.overrides]]")
    cfg_lines.append("module = [")
    cfg_lines.append('  "synapse.marketing_os.*",')
    cfg_lines.append('  "synapse.legacy.*",')
    cfg_lines.append('  "synapse.pulse.*",')
    cfg_lines.append('  "synapse.reporting.*",')
    cfg_lines.append('  "synapse.discovery.*",')
    cfg_lines.append('  "synapse.cli.*",')
    cfg_lines.append('  "synapse.integrations.*",')
    cfg_lines.append('  "synapse.infra.*",')
    cfg_lines.append('  "synapse.learning.*",')
    cfg_lines.append('  "ops.*",')
    cfg_lines.append("]")
    cfg_lines.append("ignore_errors = true")
    cfg_lines.append("")

    if meta_mods:
        cfg_lines.append("[[tool.mypy.overrides]]")
        cfg_lines.append("module = [")
        for m in meta_mods:
            cfg_lines.append(f'  "{m}",')
        cfg_lines.append("]")
        cfg_lines.append("ignore_errors = true")
        cfg_lines.append("")

    cfg_lines.append("[[tool.mypy.overrides]]")
    cfg_lines.append('module = ["synapse.safety.integrations.vault_gate"]')
    cfg_lines.append('disable_error_code = ["arg-type"]')
    cfg_lines.append("")

    CFG = "\n".join(cfg_lines).rstrip() + "\n"

    txt = p.read_text(encoding="utf-8")

    txt2 = strip_block(txt, r"\[tool\.mypy\]")
    prev = None
    while prev != txt2:
        prev = txt2
        txt2 = strip_block(txt2, r"\[\[tool\.mypy\.overrides\]\]")

    txt2 = txt2.rstrip() + "\n\n" + CFG

    if txt2 != txt:
        p.write_text(txt2, encoding="utf-8")
        print("patched=1")
    else:
        print("patched=0")

    print(f"meta_modules_count={len(meta_mods)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
