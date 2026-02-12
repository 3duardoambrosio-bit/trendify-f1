from __future__ import annotations

from synapse.infra.cli_logging import cli_print

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging
logger = logging.getLogger(__name__)


__MARKER__ = "CREATIVE_ASSETS_BUILD_2026-01-14_V2"

DEFAULT_BRIEFS = Path("data/run/creative_briefs.json")
DEFAULT_TASKS = Path("data/run/publish_tasks_meta.json")
DEFAULT_ASSETS_DIR = Path("assets")
DEFAULT_MANIFEST = Path("data/run/creative_assets_manifest.json")


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(p: Path) -> Optional[Dict[str, Any]]:
    try:
        if not p.exists():
            return None
        obj = json.loads(p.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _write_json(p: Path, obj: Dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")


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


def _find_ffmpeg() -> Optional[str]:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    # Fallback: imageio-ffmpeg if available
    try:
        import imageio_ffmpeg  # type: ignore
        exe2 = imageio_ffmpeg.get_ffmpeg_exe()
        if exe2 and Path(exe2).exists():
            return exe2
    except Exception as e:
        logger.debug("suppressed exception", exc_info=True)

    return None


def _default_fontfile() -> Optional[str]:
    candidates = [
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\Arial.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\SegoeUI.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            return str(Path(c).resolve())
    return None


def _collect_from_briefs(briefs_obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    briefs = briefs_obj.get("briefs", [])
    if not isinstance(briefs, list):
        return []
    out: List[Dict[str, Any]] = []
    for b in briefs:
        if not isinstance(b, dict):
            continue
        utm = _safe_str(b.get("utm_content"), "")
        if not utm:
            continue
        angle = _safe_str(b.get("angle"), "unknown")
        fmt = _safe_str(b.get("format"), "unknown")
        hook_id = _safe_str(b.get("hook_id"), "")

        script = b.get("script", {}) if isinstance(b.get("script"), dict) else {}
        structure = script.get("structure", [])
        hook_line = ""
        prob_line = ""
        for beat in structure if isinstance(structure, list) else []:
            if not isinstance(beat, dict):
                continue
            bt = _safe_str(beat.get("beat"), "").upper()
            sc = _safe_str(beat.get("script"), "")
            if bt == "HOOK" and not hook_line:
                hook_line = sc
            if bt == "PROBLEM" and not prob_line:
                prob_line = sc

        out.append({
            "utm_content": utm,
            "angle": angle,
            "format": fmt,
            "hook_id": hook_id,
            "hook": hook_line,
            "problem": prob_line,
        })
    return out


def _collect_from_tasks(tasks_obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    tasks = tasks_obj.get("tasks", [])
    if not isinstance(tasks, list):
        return []
    out: List[Dict[str, Any]] = []
    for t in tasks:
        if not isinstance(t, dict):
            continue
        utm = _safe_str(t.get("utm_content"), "")
        if not utm:
            continue
        naming = t.get("naming", {}) if isinstance(t.get("naming"), dict) else {}
        copy = t.get("copy", {}) if isinstance(t.get("copy"), dict) else {}
        out.append({
            "utm_content": utm,
            "angle": _safe_str(t.get("angle"), "unknown"),
            "format": _safe_str(t.get("format"), "unknown"),
            "hook_id": _safe_str(t.get("hook_id"), ""),
            "hook": "",
            "problem": "",
            "primary_text": _safe_str(copy.get("primary_text"), ""),
            "headline": _safe_str(copy.get("headline"), ""),
            "campaign": _safe_str(naming.get("campaign"), ""),
        })
    return out


def _build_text_payload(item: Dict[str, Any], offer: str) -> str:
    utm = _safe_str(item.get("utm_content"), "UNKNOWN")
    angle = _safe_str(item.get("angle"), "unknown")
    fmt = _safe_str(item.get("format"), "unknown")
    hook = _safe_str(item.get("hook"), "") or _safe_str(item.get("headline"), "")
    prob = _safe_str(item.get("problem"), "")
    primary = _safe_str(item.get("primary_text"), "")

    lines: List[str] = []
    if hook:
        lines.append(hook)
        lines.append("")
    if prob:
        lines.append(prob)
        lines.append("")
    if offer:
        lines.append(offer)
        lines.append("")
    if primary and primary not in lines:
        lines.append(primary[:220])
        lines.append("")
    lines.append(f"[{utm}]  angle={angle}  format={fmt}")
    lines.append("CTA: Compra ahora")
    return "\n".join(lines).strip() + "\n"


def _ffmpeg_escape_path(p: Path) -> str:
    """
    ffmpeg filter args use ':' as separators (drawtext opts), so Windows drive 'C:' can break parsing.
    Best strategy:
      1) prefer relative path (no drive letter)
      2) else escape ':' as '\:'
    """
    try:
        rel = p.resolve().relative_to(Path.cwd().resolve())
        s = rel.as_posix()
    except Exception:
        s = p.resolve().as_posix()

    # escape colon for ffmpeg filter parsing
    s = s.replace(":", r"\:")
    # escape single quote if any (rare but possible)
    s = s.replace("'", r"\'")
    return s


def _run_ffmpeg_make_blank(
    ffmpeg: str,
    out_mp4: Path,
    seconds: int,
    size: str,
    fps: int,
) -> Tuple[bool, str]:
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel", "error",
        "-f", "lavfi",
        "-i", f"color=c=black:s={size}:r={fps}",
        "-f", "lavfi",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", str(int(seconds)),
        "-shortest",
        "-pix_fmt", "yuv420p",
        str(out_mp4.resolve()),
    ]
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if cp.returncode != 0:
            err = (cp.stderr or cp.stdout or "").strip()
            return False, err[:1600]
        if not out_mp4.exists() or out_mp4.stat().st_size <= 0:
            return False, "ffmpeg produced empty output (blank)"
        return True, "OK"
    except Exception as e:
        return False, f"exception: {e}"


def _run_ffmpeg_make_stub(
    ffmpeg: str,
    out_mp4: Path,
    textfile: Path,
    seconds: int,
    size: str,
    fps: int,
    fontfile: Optional[str],
    fontsize: int,
) -> Tuple[bool, str]:
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    textfile.parent.mkdir(parents=True, exist_ok=True)

    tf = _ffmpeg_escape_path(textfile)
    drawtext = f"drawtext=textfile='{tf}':reload=1:fontcolor=white:fontsize={fontsize}:line_spacing=12:x=(w-text_w)/2:y=(h-text_h)/2"
    if fontfile:
        ff = _ffmpeg_escape_path(Path(fontfile))
        drawtext = f"drawtext=fontfile='{ff}':textfile='{tf}':reload=1:fontcolor=white:fontsize={fontsize}:line_spacing=12:x=(w-text_w)/2:y=(h-text_h)/2"

    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel", "error",
        "-f", "lavfi",
        "-i", f"color=c=black:s={size}:r={fps}",
        "-f", "lavfi",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", str(int(seconds)),
        "-vf", drawtext,
        "-shortest",
        "-pix_fmt", "yuv420p",
        str(out_mp4.resolve()),
    ]

    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if cp.returncode != 0:
            err = (cp.stderr or cp.stdout or "").strip()
            return False, err[:1600]
        if not out_mp4.exists() or out_mp4.stat().st_size <= 0:
            return False, "ffmpeg produced empty output"
        return True, "OK"
    except Exception as e:
        return False, f"exception: {e}"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="synapse.creative_assets_build", description="Generate stub video assets for Phase-1 publisher.")
    ap.add_argument("--briefs", default=str(DEFAULT_BRIEFS), help="Path to creative_briefs.json (preferred).")
    ap.add_argument("--tasks", default=str(DEFAULT_TASKS), help="Fallback path to publish_tasks_meta.json.")
    ap.add_argument("--assets-dir", default=str(DEFAULT_ASSETS_DIR), help="Assets output directory.")
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Manifest output JSON.")
    ap.add_argument("--offer", default="Oferta limitada. Stock variable.", help="Offer line shown on stub videos.")
    ap.add_argument("--seconds", type=int, default=9, help="Stub video duration (seconds).")
    ap.add_argument("--size", default="1080x1920", help="Video size, e.g. 1080x1920.")
    ap.add_argument("--fps", type=int, default=30, help="Frames per second.")
    ap.add_argument("--fontsize", type=int, default=60, help="Font size for drawtext.")
    ap.add_argument("--force", action="store_true", help="Overwrite existing mp4 assets.")
    args = ap.parse_args(argv)

    briefs_path = Path(args.briefs).resolve()
    tasks_path = Path(args.tasks).resolve()
    assets_dir = Path(args.assets_dir).resolve()
    manifest_path = Path(args.manifest).resolve()

    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found (unexpected). Ensure PATH is updated and restart the shell.")

    fontfile = _default_fontfile()

    # Ensure base dirs exist
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "_text").mkdir(parents=True, exist_ok=True)

    briefs_obj = _read_json(briefs_path) or {}
    items = _collect_from_briefs(briefs_obj)

    source = "briefs"
    if not items:
        tasks_obj = _read_json(tasks_path) or {}
        items = _collect_from_tasks(tasks_obj)
        source = "tasks"

    if not items:
        raise RuntimeError(f"No items found in briefs ({briefs_path}) nor tasks ({tasks_path}).")

    out_items: List[Dict[str, Any]] = []
    built = 0
    skipped = 0
    failed = 0

    text_dir = assets_dir / "_text"

    for it in items:
        utm = _safe_str(it.get("utm_content"), "UNKNOWN")
        out_mp4 = assets_dir / f"{utm}.mp4"
        textfile = text_dir / f"{utm}.txt"

        if out_mp4.exists() and out_mp4.stat().st_size > 0 and not args.force:
            skipped += 1
            out_items.append({
                "utm_content": utm,
                "path": str(out_mp4),
                "status": "SKIPPED_EXISTS",
                "bytes": int(out_mp4.stat().st_size),
                "sha256": _sha256_file(out_mp4),
            })
            continue

        payload_text = _build_text_payload(it, _safe_str(args.offer))
        textfile.write_text(payload_text, encoding="utf-8")

        ok, msg = _run_ffmpeg_make_stub(
            ffmpeg=ffmpeg,
            out_mp4=out_mp4,
            textfile=textfile,
            seconds=int(args.seconds),
            size=_safe_str(args.size),
            fps=int(args.fps),
            fontfile=fontfile,
            fontsize=int(args.fontsize),
        )

        mode_used = "drawtext"
        drawtext_error = ""
        if not ok:
            # Failsafe: still create a valid MP4 so pipelines don't die.
            drawtext_error = msg
            ok2, msg2 = _run_ffmpeg_make_blank(
                ffmpeg=ffmpeg,
                out_mp4=out_mp4,
                seconds=int(args.seconds),
                size=_safe_str(args.size),
                fps=int(args.fps),
            )
            if ok2:
                ok = True
                msg = f"DRAWTEXT_FAIL_FALLBACK_BLANK: {drawtext_error}"
                mode_used = "blank_fallback"
            else:
                msg = f"DRAWTEXT_ERR: {drawtext_error} | BLANK_ERR: {msg2}"
                mode_used = "failed"

        if ok:
            built += 1
            out_items.append({
                "utm_content": utm,
                "path": str(out_mp4),
                "status": "BUILT",
                "mode": mode_used,
                "note": msg if mode_used != "drawtext" else "",
                "bytes": int(out_mp4.stat().st_size),
                "sha256": _sha256_file(out_mp4),
                "ffmpeg": ffmpeg,
                "fontfile": fontfile or "",
                "textfile": str(textfile),
            })
        else:
            failed += 1
            out_items.append({
                "utm_content": utm,
                "path": str(out_mp4),
                "status": "FAIL",
                "mode": mode_used,
                "error": msg,
                "ffmpeg": ffmpeg,
                "fontfile": fontfile or "",
                "textfile": str(textfile),
            })

    manifest = {
        "marker": __MARKER__,
        "ts": _utc_now_z(),
        "source": source,
        "briefs_path": str(briefs_path),
        "tasks_path": str(tasks_path),
        "assets_dir": str(assets_dir),
        "counts": {"items": len(items), "built": built, "skipped": skipped, "failed": failed},
        "assets": out_items,
        "notes": {
            "purpose": "Stub assets to unblock Meta publisher validate/execute pipeline",
            "mode": "template_stub_with_failsafe",
            "video_spec": {"seconds": int(args.seconds), "size": _safe_str(args.size), "fps": int(args.fps)},
            "failsafe": "If drawtext fails, a blank MP4 is generated so validate can pass (dev unblock).",
        },
    }
    _write_json(manifest_path, manifest)

    status = "OK" if failed == 0 else "FAIL"
    cli_print(json.dumps({
        "marker": __MARKER__,
        "ts": manifest["ts"],
        "status": status,
        "ffmpeg": ffmpeg,
        "fontfile": fontfile or "",
        "assets_dir": str(assets_dir),
        "manifest": str(manifest_path),
        "counts": manifest["counts"],
    }, ensure_ascii=False, indent=2, sort_keys=True))

    return 0 if status == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
