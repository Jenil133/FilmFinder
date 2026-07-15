"""Generate 240px JPEG thumbnails for result cards.

Thumbnails ARE committed to the repo (the deployed app serves them from it);
raw frames are not.

Usage:
    python make_thumbs.py --frames-dir frames/dev --out thumbs/dev
    python make_thumbs.py --frames-dir frames/match01 --out thumbs/match01
"""

import argparse
from pathlib import Path

from PIL import Image


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frames-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--width", type=int, default=240)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = sorted(Path(args.frames_dir).glob("*.jpg"))
    if not frames:
        raise SystemExit(f"No frames in {args.frames_dir}")

    made = skipped = 0
    for jpg in frames:
        dst = out_dir / jpg.name
        if dst.exists():
            skipped += 1
            continue
        with Image.open(jpg) as img:
            h = round(img.height * args.width / img.width)
            img.resize((args.width, h), Image.LANCZOS).save(
                dst, "JPEG", quality=80, optimize=True)
        made += 1

    total_kb = sum(f.stat().st_size for f in out_dir.glob("*.jpg")) // 1024
    print(f"{made} thumbnails made, {skipped} already existed -> {out_dir} "
          f"({total_kb} KB total)")


if __name__ == "__main__":
    main()
