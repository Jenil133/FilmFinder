"""Extract frames from the match video with ffmpeg.

1 frame per 2 seconds, 768 px wide. Writes meta.json alongside the frames
recording the slice offset inside the FULL video, so downstream timestamps
are global (they must match what the YouTube iframe seeks to).

Usage (Phase 1 — the 12-minute kill-test slice):
    python extract_frames.py --video match01.mp4 --start 00:20:00 --duration 720 --out frames/dev

Usage (Phase 2 — full match):
    python extract_frames.py --video match01.mp4 --out frames/match01
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def parse_ts(ts: str) -> int:
    """'HH:MM:SS' | 'MM:SS' | plain seconds -> seconds (int)."""
    if ":" not in ts:
        return int(float(ts))
    parts = [float(p) for p in ts.split(":")]
    secs = 0.0
    for p in parts:
        secs = secs * 60 + p
    return int(secs)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video", required=True)
    ap.add_argument("--start", default="0", help="slice start in the full video (HH:MM:SS or seconds)")
    ap.add_argument("--duration", type=int, default=0, help="slice length in seconds (0 = to the end)")
    ap.add_argument("--out", required=True, help="output dir for frames")
    ap.add_argument("--interval", type=int, default=2, help="seconds between frames")
    ap.add_argument("--width", type=int, default=768)
    args = ap.parse_args()

    video = Path(args.video)
    if not video.exists():
        sys.exit(f"Video not found: {video}")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    offset = parse_ts(args.start)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(offset)]
    if args.duration:
        cmd += ["-t", str(args.duration)]
    cmd += [
        "-i", str(video),
        "-vf", f"fps=1/{args.interval},scale={args.width}:-2",
        "-q:v", "2",
        str(out_dir / "frame_%04d.jpg"),
    ]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)

    frames = sorted(out_dir.glob("frame_*.jpg"))
    meta = {
        "source_video": video.name,
        "offset_seconds": offset,
        "interval_seconds": args.interval,
        "duration_seconds": args.duration or None,
        "width": args.width,
        "frame_count": len(frames),
        "timestamp_rule": "t_global = offset_seconds + (frame_index - 1) * interval_seconds",
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"{len(frames)} frames -> {out_dir} · offset {offset}s · meta.json written")


if __name__ == "__main__":
    main()
