from __future__ import annotations

from synapse.infra.cli_logging import cli_print

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging
logger = logging.getLogger(__name__)

__MARKER__ = "CREATIVE_FACTORY_ULTRA_2026-01-14_V1"

DEFAULT_BRIEFS = Path("data/run/creative_briefs.json")
DEFAULT_ASSETS_DIR = Path("assets")
DEFAULT_MANIFEST = Path("data/run/assets_manifest.json")
DEFAULT_RUN = Path("data/run/creative_factory_run.json")

# Conservative: avoid obvious policy landmines in generated overlays/copy.
BANNED_TERMS = [
    "cura", "curar", "tratamiento garantizado", "garantizado", "100% garantizado",
    "resultados garantizados", "pierde peso", "baja de peso", "milagro",
]

# ---------- utils ----------
def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    obj = json.loads(path.read_text(encoding="utf-8"))
    return obj if isinstance(obj, dict) else {}

def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")

def _safe_str(x: Any, default: str = "") -> str:
    if x is None:
        return default
    s = str(x).strip()
    return s if s else default

def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()

def _sha256_obj(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()

def _which(cmd: str) -> Optional[str]:
    return shutil.which(cmd)

def _find_windows_font() -> Optional[str]:
    # Hardening: drawtext often fails if font isn't resolvable.
    # Prefer a known Windows font path if exists.
    candidates = [
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\calibri.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None

def _ffmpeg_escape_text(s: str) -> str:
    """
    Escape text for ffmpeg drawtext. We keep it simple and defensive.
    - remove newlines
    - escape backslash, colon, apostrophe, percent
    """
    s = s.replace("\n", " ").replace("\r", " ").strip()
    s = s.replace("\\", r"\\")
    s = s.replace(":", r"\:")
    s = s.replace("'", r"\'")
    s = s.replace("%", r"\%")
    return s

def _clean_policy_text(s: str) -> Tuple[str, List[str]]:
    """
    Return (cleaned_text, flags)
    We don't try to be perfect; we just remove obvious risky tokens.
    """
    flags: List[str] = []
    t = _safe_str(s, "")
    low = t.lower()
    for term in BANNED_TERMS:
        if term in low:
            flags.append(f"banned_term:{term}")
            # blunt removal (keep meaning)
            t = t.replace(term, "").replace(term.upper(), "").replace(term.capitalize(), "")
            low = t.lower()
    # collapse whitespace
    t = " ".join(t.split())
    return t, flags

def _ffprobe_json(p: Path) -> Dict[str, Any]:
    """
    Best-effort metadata. If ffprobe not available, return {}.
    """
    if not _which("ffprobe"):
        return {}
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-print_format", "json",
            "-show_format", "-show_streams",
            str(p),
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        obj = json.loads(out)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}

def _extract_video_meta(ffp: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse ffprobe json -> compact meta.
    """
    meta: Dict[str, Any] = {}
    streams = ffp.get("streams", [])
    fmt = ffp.get("format", {}) if isinstance(ffp.get("format"), dict) else {}
    if isinstance(fmt, dict):
        meta["duration_s"] = float(fmt.get("duration", 0.0) or 0.0)
        meta["size_bytes"] = int(float(fmt.get("size", 0) or 0))
        meta["bit_rate"] = _safe_str(fmt.get("bit_rate"), "")
    if isinstance(streams, list):
        v = None
        a = None
        for st in streams:
            if not isinstance(st, dict):
                continue
            if st.get("codec_type") == "video" and v is None:
                v = st
            if st.get("codec_type") == "audio" and a is None:
                a = st
        if isinstance(v, dict):
            meta["width"] = int(v.get("width") or 0)
            meta["height"] = int(v.get("height") or 0)
            meta["fps"] = _safe_str(v.get("avg_frame_rate"), "")
            meta["vcodec"] = _safe_str(v.get("codec_name"), "")
        if isinstance(a, dict):
            meta["acodec"] = _safe_str(a.get("codec_name"), "")
            meta["audio_present"] = True
        else:
            meta["audio_present"] = False
    return meta

# ---------- domain ----------
@dataclass
class Beat:
    name: str
    text: str
    t0: float
    t1: float

def _pick_text_from_brief(brief: Dict[str, Any]) -> Dict[str, str]:
    """
    Best-effort: derive HOOK/PROBLEM/DEMO/OFFER/CTA from structure.
    """
    script = brief.get("script", {}) if isinstance(brief.get("script"), dict) else {}
    structure = script.get("structure", [])
    out = {"HOOK": "", "PROBLEM": "", "DEMO": "", "OFFER": "", "CTA": ""}
    if isinstance(structure, list):
        for b in structure:
            if not isinstance(b, dict):
                continue
            beat = _safe_str(b.get("beat"), "").upper()
            txt = _safe_str(b.get("script"), "")
            if beat in out and not out[beat] and txt:
                out[beat] = txt
    # fallback: on_screen_text list
    ost = script.get("on_screen_text", [])
    if isinstance(ost, list) and any(_safe_str(x) for x in ost):
        # if HOOK empty, steal first line
        if not out["HOOK"]:
            out["HOOK"] = _safe_str(ost[0], "")
    return out

def _build_beats(brief: Dict[str, Any], duration_s: float) -> Tuple[List[Beat], List[str]]:
    """
    Build a deterministic beat timeline.
    """
    flags: List[str] = []
    txt = _pick_text_from_brief(brief)

    # business-y safe defaults
    offer_default = _safe_str(brief.get("offer"), "") or "Oferta limitada. Stock variable."
    cta_default = "Compra ahora."

    hook, f1 = _clean_policy_text(txt.get("HOOK", "") or "¿Te duele y no sabes por qué?")
    prob, f2 = _clean_policy_text(txt.get("PROBLEM", "") or "Lo normal se vuelve incómodo: agarrar, cargar, trabajar.")
    demo, f3 = _clean_policy_text(txt.get("DEMO", "") or "Solución simple: soporte + alivio + comodidad.")
    offer, f4 = _clean_policy_text(txt.get("OFFER", "") or offer_default)
    cta, f5 = _clean_policy_text(txt.get("CTA", "") or cta_default)
    flags.extend(f1 + f2 + f3 + f4 + f5)

    # timeline: keep simple and platform-friendly
    # 0-3 HOOK, 3-6 PROBLEM, 6-11 DEMO, 11-14 OFFER, 14-end CTA
    t = max(10.0, float(duration_s))
    beats = [
        Beat("HOOK", hook, 0.0, min(3.0, t)),
        Beat("PROBLEM", prob, min(3.0, t), min(6.0, t)),
        Beat("DEMO", demo, min(6.0, t), min(11.0, t)),
        Beat("OFFER", offer, min(11.0, t), min(14.0, t)),
        Beat("CTA", cta, min(14.0, t), t),
    ]
    # remove empty beats
    beats = [b for b in beats if b.text and b.t1 > b.t0]
    return beats, flags

def _build_drawtext_filters(
    beats: List[Beat],
    fontfile: Optional[str],
    w: int,
    h: int,
) -> str:
    """
    Single pass drawtext with enable='between(t,...)' per beat.
    """
    # Safe margins and sizes
    fs_main = max(46, int(h * 0.035))     # ~67 for 1920
    fs_small = max(28, int(h * 0.020))
    y_main = int(h * 0.18)
    y_sub = int(h * 0.78)

    parts: List[str] = []
    # subtle vignette/contrast helps readability
    parts.append(f"format=yuv420p")
    parts.append("eq=contrast=1.08:brightness=0.02:saturation=1.05")

    # Brand/footer always on
    brand = _ffmpeg_escape_text("TrendifyHub")
    ff = f":fontfile='{_ffmpeg_escape_text(fontfile)}'" if fontfile else ""
    parts.append(
        "drawtext"
        f"{ff}:text='{brand}':x=40:y={y_sub}:fontsize={fs_small}:fontcolor=white@0.65"
        ":shadowcolor=black@0.6:shadowx=2:shadowy=2"
    )

    # Beat overlays
    for b in beats:
        text = _ffmpeg_escape_text(b.text)
        enable = f"between(t,{b.t0:.2f},{b.t1:.2f})"
        # center main text
        parts.append(
            "drawtext"
            f"{ff}:text='{text}':x=(w-text_w)/2:y={y_main}:fontsize={fs_main}:fontcolor=white"
            ":box=1:boxcolor=black@0.45:boxborderw=24"
            ":shadowcolor=black@0.6:shadowx=2:shadowy=2"
            f":enable='{enable}'"
        )

    return ",".join(parts)

def _render_ffmpeg(
    out_path: Path,
    beats: List[Beat],
    duration_s: float,
    size: str,
    fps: int,
    fontfile: Optional[str],
) -> Tuple[bool, str]:
    """
    Render a vertical MP4 using FFmpeg sources only (no external media needed).
    """
    if not _which("ffmpeg"):
        return False, "ffmpeg_not_found"

    # parse size WxH
    try:
        w_str, h_str = size.lower().split("x")
        w, h = int(w_str), int(h_str)
    except Exception:
        return False, "bad_size"

    vf = _build_drawtext_filters(beats, fontfile=fontfile, w=w, h=h)

    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Video source + silent audio (helps platform ingestion)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:d={duration_s}:r={fps}",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-vf", vf,
        "-t", str(duration_s),
        "-shortest",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-profile:v", "high",
        "-level", "4.1",
        "-movflags", "+faststart",
        "-c:a", "aac",
        "-b:a", "128k",
        str(out_path),
    ]

    try:
        subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        return True, "ok"
    except subprocess.CalledProcessError as e:
        # fallback: retry without fontfile (font resolution issues)
        if fontfile:
            try:
                vf2 = _build_drawtext_filters(beats, fontfile=None, w=w, h=h)
                cmd2 = cmd[:]
                cmd2[cmd2.index(vf)] = vf2  # replace vf string
                subprocess.check_output(cmd2, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
                return True, "ok_font_fallback"
            except Exception:
                return False, "ffmpeg_failed"
        return False, "ffmpeg_failed"
    except Exception:
        return False, "ffmpeg_failed"

def _qa_asset(path: Path, min_size_bytes: int, expected_size: str, max_duration_s: float) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    QA gate:
    - file exists
    - size > min
    - duration <= max
    - resolution matches expected (best-effort)
    """
    issues: List[str] = []
    meta: Dict[str, Any] = {}

    if not path.exists():
        return False, ["missing_file"], meta
    try:
        sizeb = path.stat().st_size
        if sizeb < min_size_bytes:
            issues.append(f"too_small_bytes:{sizeb}")
    except Exception:
        issues.append("stat_failed")

    ffp = _ffprobe_json(path)
    meta = _extract_video_meta(ffp) if ffp else {}
    if meta.get("duration_s") is not None and float(meta.get("duration_s") or 0.0) > float(max_duration_s):
        issues.append(f"too_long:{meta.get('duration_s')}")

    # expected size check (best-effort)
    try:
        w_str, h_str = expected_size.lower().split("x")
        ew, eh = int(w_str), int(h_str)
        if meta.get("width") and meta.get("height"):
            if int(meta["width"]) != ew or int(meta["height"]) != eh:
                issues.append(f"bad_resolution:{meta.get('width')}x{meta.get('height')}")
    except Exception as e:
        logger.debug("suppressed exception", exc_info=True)

    ok = len(issues) == 0
    return ok, issues, meta

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="synapse.creative_factory", description="Render Phase-1 creative assets (ULTRA deterministic template).")
    ap.add_argument("--briefs", default=str(DEFAULT_BRIEFS), help="Path to creative_briefs.json")
    ap.add_argument("--assets-dir", default=str(DEFAULT_ASSETS_DIR), help="Output assets directory")
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Output manifest JSON")
    ap.add_argument("--run-out", default=str(DEFAULT_RUN), help="Output run report JSON")
    ap.add_argument("--limit", type=int, default=0, help="Limit number of briefs rendered (0=all)")
    ap.add_argument("--only-utm", default="", help="Render only this utm_content")
    ap.add_argument("--duration", type=float, default=15.0, help="Video duration seconds")
    ap.add_argument("--size", default="1080x1920", help="Video size WxH")
    ap.add_argument("--fps", type=int, default=30, help="FPS")
    ap.add_argument("--min-bytes", type=int, default=50_000, help="Minimum output bytes for QA gate")
    ap.add_argument("--max-duration", type=float, default=25.0, help="Max duration allowed for QA gate")
    ap.add_argument("--dry-run", action="store_true", help="No rendering; just plan + report")
    args = ap.parse_args(argv)

    briefs_path = Path(args.briefs).resolve()
    assets_dir = Path(args.assets_dir).resolve()
    manifest_path = Path(args.manifest).resolve()
    run_out = Path(args.run_out).resolve()

    src = _read_json(briefs_path)
    briefs = src.get("briefs", [])
    if not isinstance(briefs, list):
        briefs = []

    # filter / limit
    if _safe_str(args.only_utm):
        briefs = [b for b in briefs if isinstance(b, dict) and _safe_str(b.get("utm_content")) == _safe_str(args.only_utm)]
    if args.limit and args.limit > 0:
        briefs = briefs[: args.limit]

    ffmpeg_ok = bool(_which("ffmpeg"))
    fontfile = _find_windows_font()

    plan_items: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    manifest_items: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for b in briefs:
        if not isinstance(b, dict):
            continue
        utm = _safe_str(b.get("utm_content"), "UNKNOWN")
        hook_id = _safe_str(b.get("hook_id"), "")
        angle = _safe_str(b.get("angle"), "")
        fmt = _safe_str(b.get("format"), "")

        beats, policy_flags = _build_beats(b, duration_s=float(args.duration))
        out_mp4 = assets_dir / f"{utm}.mp4"

        plan_obj = {
            "utm_content": utm,
            "out_mp4": str(out_mp4),
            "beats": [{"name": x.name, "t0": x.t0, "t1": x.t1, "text": x.text} for x in beats],
            "policy_flags": policy_flags,
        }
        plan_items.append(plan_obj)

        if args.dry_run:
            results.append({"utm_content": utm, "status": "DRY", "out_mp4": str(out_mp4), "policy_flags": policy_flags})
            continue

        if not ffmpeg_ok:
            err = {"utm_content": utm, "error": "ffmpeg_not_found"}
            errors.append(err)
            results.append({"utm_content": utm, "status": "FAIL", "error": err["error"]})
            continue

        ok, reason = _render_ffmpeg(
            out_path=out_mp4,
            beats=beats,
            duration_s=float(args.duration),
            size=_safe_str(args.size, "1080x1920"),
            fps=int(args.fps),
            fontfile=fontfile,
        )
        if not ok:
            err = {"utm_content": utm, "error": reason}
            errors.append(err)
            results.append({"utm_content": utm, "status": "FAIL", "error": reason, "out_mp4": str(out_mp4)})
            continue

        qa_ok, qa_issues, meta = _qa_asset(
            out_mp4,
            min_size_bytes=int(args.min_bytes),
            expected_size=_safe_str(args.size, "1080x1920"),
            max_duration_s=float(args.max_duration),
        )
        sha = _sha256_file(out_mp4) if out_mp4.exists() else ""

        item = {
            "utm_content": utm,
            "hook_id": hook_id,
            "angle": angle,
            "format": fmt,
            "path": str(out_mp4),
            "sha256": sha,
            "policy_flags": policy_flags,
            "qa": {"ok": qa_ok, "issues": qa_issues},
            "meta": meta,
            "render_marker": __MARKER__,
            "render_ts": _utc_now_z(),
        }
        manifest_items.append(item)

        if not qa_ok:
            errors.append({"utm_content": utm, "error": "qa_fail", "issues": qa_issues})
            results.append({"utm_content": utm, "status": "FAIL", "error": "qa_fail", "issues": qa_issues, "out_mp4": str(out_mp4)})
            continue

        results.append({"utm_content": utm, "status": "OK", "out_mp4": str(out_mp4), "sha256": sha, "render": reason})

    manifest = {
        "marker": __MARKER__,
        "ts": _utc_now_z(),
        "source_briefs": str(briefs_path),
        "assets_dir": str(assets_dir),
        "count": len(manifest_items),
        "items": manifest_items,
        "manifest_hash": _sha256_obj({"items": manifest_items}),
        "notes": {
            "deterministic_template_renderer": True,
            "ai_provider_not_required_for_v1": True,
            "upgrade_path": "Hybrid + AI clips + FFmpeg assembly",
        }
    }

    run = {
        "marker": __MARKER__,
        "ts": _utc_now_z(),
        "status": "OK" if not errors else "FAIL",
        "briefs_path": str(briefs_path),
        "counts": {"planned": len(plan_items), "results": len(results), "errors": len(errors)},
        "env": {"ffmpeg_present": ffmpeg_ok, "ffprobe_present": bool(_which("ffprobe")), "fontfile": fontfile or ""},
        "plan": plan_items,
        "results": results,
        "errors": errors,
    }

    _write_json(manifest_path, manifest)
    _write_json(run_out, run)

    cli_print(json.dumps({
        "marker": __MARKER__,
        "ts": run["ts"],
        "status": run["status"],
        "briefs": str(briefs_path),
        "assets_dir": str(assets_dir),
        "manifest": str(manifest_path),
        "run": str(run_out),
        "counts": run["counts"],
    }, ensure_ascii=False, indent=2, sort_keys=True))

    # Exit code as gate (CI-friendly)
    return 0 if run["status"] == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
