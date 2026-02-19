import ast, re, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SYN  = ROOT / "synapse"

TARGETS = {
    "int":   "except (ValueError, TypeError)",
    "float": "except (ValueError, TypeError)",
    "json.loads": "except (json.JSONDecodeError, TypeError)",
    "importlib.import_module": "except (ModuleNotFoundError, ImportError)",
}

def full_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = full_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""

def call_name(node):
    if not isinstance(node, ast.Call):
        return ""
    return full_name(node.func)

def safe_read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")

def safe_write(p: Path, s: str) -> None:
    p.write_text(s, encoding="utf-8", newline="\n")

def patch_except_header(line: str, new_except: str) -> str:
    # line like: "    except Exception:" or "    except Exception as e:"
    # Replace ONLY the "except Exception" part.
    return re.sub(r"\bexcept\s+Exception\b", new_except, line, count=1)

def maybe_target_try(try_node: ast.Try):
    # Only narrow when:
    # - handler catches Exception (single)
    # - try body has exactly 1 statement which is Assign/Expr with simple Call
    # - handler line contains "except Exception"
    if len(try_node.handlers) != 1:
        return None
    h = try_node.handlers[0]
    if not isinstance(h.type, ast.Name) or h.type.id != "Exception":
        return None
    if len(try_node.body) != 1:
        return None

    stmt = try_node.body[0]
    call = None
    if isinstance(stmt, ast.Assign):
        call = stmt.value
    elif isinstance(stmt, ast.Expr):
        call = stmt.value

    name = call_name(call) if call is not None else ""
    if name in ("int", "float"):
        return TARGETS[name]
    if name in ("importlib.import_module",):
        return TARGETS[name]
    if name in ("json.loads",):
        return TARGETS[name]
    return None

def run():
    py_files = [p for p in SYN.rglob("*.py") if p.is_file()]
    changed_files = 0
    changed_handlers = 0
    skipped_parse = 0
    notes = []

    for p in py_files:
        src = safe_read(p)
        try:
            tree = ast.parse(src)
        except Exception as e:
            skipped_parse += 1
            notes.append({"file": str(p.relative_to(ROOT)), "reason": f"parse_fail:{type(e).__name__}"})
            continue

        lines = src.splitlines()
        edits = []  # list of (lineno0, new_line)

        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                new_except = maybe_target_try(node)
                if not new_except:
                    continue
                # find handler lineno (1-based)
                h = node.handlers[0]
                if not getattr(h, "lineno", None):
                    continue
                i = h.lineno - 1
                if i < 0 or i >= len(lines):
                    continue
                if "except Exception" not in lines[i]:
                    continue
                patched = patch_except_header(lines[i], new_except)
                if patched != lines[i]:
                    edits.append((i, patched))

        if not edits:
            continue

        # apply edits (dedupe by lineno)
        dedup = {}
        for i, nl in edits:
            dedup[i] = nl
        for i in sorted(dedup.keys()):
            lines[i] = dedup[i]
            changed_handlers += 1

        safe_write(p, "\n".join(lines) + ("\n" if not src.endswith("\n") else ""))
        changed_files += 1

    print("CHANGED_FILES=", changed_files)
    print("CHANGED_HANDLERS=", changed_handlers)
    print("SKIPPED_PARSE=", skipped_parse)
    if notes[:10]:
        print("NOTES_SAMPLE=", json.dumps(notes[:10], indent=2))

if __name__ == "__main__":
    run()
