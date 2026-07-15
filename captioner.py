"""FilmFinder frame captioner.

Sends batches of soccer-match frames to a vision LLM (Gemini Flash primary,
Groq fallback) and appends one structured JSON line per frame to a JSONL cache.

Resumable by design: frames whose filename already appears in the output
JSONL are skipped, and a partial trailing line left by a crash mid-write is
repaired on startup — so killing and restarting the job adds zero duplicate
lines. Stats (frames/min, token usage) are written next to the output file
(<out>_stats.json) — Phase 2's overnight ETA is computed from them.

Usage:
    python captioner.py --frames-dir frames/dev --out captions_dev.jsonl
    python captioner.py --frames-dir frames/dev --out captions_dev.jsonl --provider groq
"""

import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# Frozen 2026-07-15 after the 5/5 kill-test pass — the full-match overnight run
# uses this exact prompt. No edits after the run starts (Phase 2 rule).
PROMPT_VERSION = "v1-final"

ACTIONS = [
    "corner", "free_kick", "penalty", "throw_in", "goal_kick", "shot",
    "save", "goal", "celebration", "tackle", "header", "dribble",
    "foul", "offside", "kickoff", "open_play", "break_or_crowd",
]

ZONES = ["defensive_third", "midfield", "attacking_third", "goal_area", "unknown"]


def build_prompt(n_frames: int, interval_s: int) -> str:
    return f"""You are a soccer match analyst. You are given {n_frames} still frames \
taken from a soccer match, in chronological order, roughly {interval_s} seconds apart.

For EACH frame, in the same order, produce one JSON object with exactly these keys:
- "action": the single most salient event visible. MUST be one of: {json.dumps(ACTIONS)}.
  Use "open_play" for ordinary passing/positioning with no distinct event.
  Use "break_or_crowd" for stoppages, injuries, crowd shots, replays, or anything that is not live play.
- "description": one factual sentence (max 30 words) describing what is happening.
  ALWAYS mention the jersey colors of the players involved (e.g. "player in red", "blue goalkeeper").
- "zone": where the ball/action is. One of: {json.dumps(ZONES)}.
- "teams": the jersey colors involved, e.g. "red vs white" or "blue" or "unknown".
- "confidence": your confidence in the "action" label, 0.0 to 1.0.

Rules:
- A corner kick shows a player at the corner flag / corner arc.
- A throw-in shows a player at the sideline holding the ball above their head.
- A save shows the goalkeeper diving, catching, or blocking.
- A shot shows a player striking the ball toward goal.
- A celebration shows players hugging, arms raised, running to fans after a goal.
- If unsure between a specific action and open_play, pick the specific action only if the visual evidence is clear; otherwise open_play with lower confidence.

Return ONLY a JSON array of exactly {n_frames} objects, one per input frame, same order. No markdown, no commentary."""


# --------------------------------------------------------------------------- #
# Providers
# --------------------------------------------------------------------------- #

class GeminiCaptioner:
    name = "gemini"

    def __init__(self):
        from google import genai  # imported lazily so groq-only runs don't need it
        from google.genai import types
        self.types = types
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            sys.exit("GOOGLE_API_KEY missing — fill .env first (see .env.example)")
        self.client = genai.Client(api_key=api_key)
        # gemini-2.5-flash is rejected for new API keys; gemini-3.5-flash free
        # tier is only 20 req/day. 3.1-flash-lite is the proven captioner
        # (38 frames/min, 5/5 kill-test) — see KILLTEST.md.
        self.model = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
        self.tokens_in = 0
        self.tokens_out = 0

    def caption_batch(self, image_paths, prompt):
        parts = [
            self.types.Part.from_bytes(data=p.read_bytes(), mime_type="image/jpeg")
            for p in image_paths
        ]
        resp = self.client.models.generate_content(
            model=self.model,
            contents=parts + [prompt],
            config=self.types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
        usage = getattr(resp, "usage_metadata", None)
        if usage:
            self.tokens_in += usage.prompt_token_count or 0
            self.tokens_out += usage.candidates_token_count or 0
        return resp.text


class GroqCaptioner:
    name = "groq"

    def __init__(self):
        from groq import Groq
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            sys.exit("GROQ_API_KEY missing — fill .env first (see .env.example)")
        self.client = Groq(api_key=api_key)
        # llama-4-scout is shut down on Groq as of 2026-07-17; qwen3.6-27b is
        # the vision-capable replacement. Caps: 3 images/request (use
        # --batch-size 3) and 8000 tokens/min on the free tier — a 768px
        # 3-image batch estimates ~9k tokens, so bulk runs crawl. Groq is a
        # gap-filler, not a bulk path; for volume wait for the Gemini daily
        # quota reset (midnight PT) instead.
        self.model = os.environ.get("GROQ_MODEL", "qwen/qwen3.6-27b")
        self.tokens_in = 0
        self.tokens_out = 0

    def caption_batch(self, image_paths, prompt):
        content = [{"type": "text", "text": prompt}]
        for p in image_paths:
            b64 = base64.b64encode(p.read_bytes()).decode()
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            })
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": content}],
            temperature=0.2,
        )
        if resp.usage:
            self.tokens_in += resp.usage.prompt_tokens or 0
            self.tokens_out += resp.usage.completion_tokens or 0
        return resp.choices[0].message.content


# --------------------------------------------------------------------------- #
# Parsing & validation
# --------------------------------------------------------------------------- #

def parse_captions(raw_text, expected: int):
    """Parse the model response into a list of caption dicts, or None on failure."""
    if raw_text is None:  # blocked/empty response
        return None
    # qwen3.6 (Groq fallback) is a thinking model — drop reasoning preamble
    text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, list) or len(data) != expected:
        return None
    cleaned = []
    for item in data:
        if not isinstance(item, dict):
            return None
        action = str(item.get("action", "open_play")).strip().lower()
        try:
            conf = float(item.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        entry = {
            "action": action if action in ACTIONS else "open_play",
            "description": str(item.get("description", "")).strip(),
            "zone": item.get("zone", "unknown"),
            "teams": item.get("teams", "unknown"),
            "confidence": conf,
        }
        if action not in ACTIONS:
            entry["raw_action"] = action  # keep what the model actually said
        cleaned.append(entry)
    return cleaned


def frame_index(path: Path) -> int:
    # Trailing digit group only: 'match01_frame_0360' must yield 360, not 1.
    m = re.search(r"(\d+)$", path.stem)
    if not m:
        sys.exit(f"Cannot parse frame index from filename: {path.name}")
    return int(m.group(1))


def repair_tail(out_path: Path):
    """Fix a partial trailing line left by a crash mid-write, so appends never
    glue a new record onto truncated bytes."""
    if not out_path.exists():
        return
    data = out_path.read_bytes()
    if not data or data.endswith(b"\n"):
        return
    tail = data[data.rfind(b"\n") + 1:]
    try:
        json.loads(tail)
        with out_path.open("ab") as f:  # complete record, just missing newline
            f.write(b"\n")
    except json.JSONDecodeError:
        with out_path.open("rb+") as f:  # drop the partial line
            f.truncate(len(data) - len(tail))
        print(f"WARNING: dropped a partial trailing line in {out_path} "
              f"(crash recovery); the frame will be re-captioned", file=sys.stderr)


def load_done(out_path: Path) -> set:
    """Frame filenames already captioned — the resume/idempotency mechanism."""
    done = set()
    if out_path.exists():
        with out_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    done.add(json.loads(line)["frame"])
                except (json.JSONDecodeError, KeyError):
                    print(f"WARNING: skipping malformed line in {out_path}", file=sys.stderr)
    return done


# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frames-dir", required=True)
    ap.add_argument("--out", required=True, help="JSONL output (append mode, resumable)")
    ap.add_argument("--batch-size", type=int, default=5,
                    help="Frames per request (Gemini: 5 is proven; Groq qwen caps at 3)")
    ap.add_argument("--provider", choices=["gemini", "groq"], default="gemini")
    ap.add_argument("--sleep", type=float, default=6.5,
                    help="Seconds between requests (Gemini free tier is ~10 req/min)")
    ap.add_argument("--max-retries", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0, help="Caption at most N frames (0 = all)")
    args = ap.parse_args()
    if args.limit < 0:
        ap.error("--limit must be >= 0")
    if args.provider == "groq" and args.batch_size > 3:
        print(f"WARNING: Groq qwen vision rejects >3 images/request — "
              f"clamping batch size {args.batch_size} -> 3", file=sys.stderr)
        args.batch_size = 3

    load_dotenv()

    frames_dir = Path(args.frames_dir)
    out_path = Path(args.out)
    stats_path = out_path.with_name(out_path.stem + "_stats.json")
    frames = sorted(frames_dir.glob("*.jpg"), key=frame_index)
    if not frames:
        sys.exit(f"No .jpg frames found in {frames_dir}")
    indices = [frame_index(p) for p in frames]
    if len(set(indices)) != len(indices):
        sys.exit("Duplicate frame indices parsed from filenames — check frame naming")

    # Timestamp bookkeeping: extract_frames.py writes meta.json with the slice
    # offset inside the full video, so payload timestamps are global — they
    # must match what the YouTube iframe seeks to.
    meta_path = frames_dir / "meta.json"
    offset, interval = 0, 2
    video_src = frames_dir.name
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        offset = meta.get("offset_seconds", 0)
        interval = meta.get("interval_seconds", 2)
        video_src = meta.get("source_video", video_src)
    else:
        print("WARNING: no meta.json in frames dir — assuming offset 0s, interval 2s",
              file=sys.stderr)

    repair_tail(out_path)
    done = load_done(out_path)
    todo = [p for p in frames if p.name not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(frames)} frames total · {len(done)} already captioned · {len(todo)} to do")
    if not todo:
        print("Nothing to do — cache is complete. (0 new lines: idempotency holds.)")
        if stats_path.exists():
            print(f"Stats from the run that did the work: {stats_path}")
        return

    captioner = GeminiCaptioner() if args.provider == "gemini" else GroqCaptioner()
    prompt = build_prompt(args.batch_size, interval)
    print(f"Provider: {captioner.name} · model: {captioner.model} · prompt: {PROMPT_VERSION}")

    started = time.time()
    written = 0
    failed_batches = 0

    with out_path.open("a") as out_f:
        for batch_no, i in enumerate(range(0, len(todo), args.batch_size)):
            if batch_no > 0:
                time.sleep(args.sleep)  # pace every request, success or failure
            batch = todo[i: i + args.batch_size]
            batch_prompt = prompt if len(batch) == args.batch_size \
                else build_prompt(len(batch), interval)
            captions = None
            for attempt in range(1, args.max_retries + 1):
                try:
                    raw = captioner.caption_batch(batch, batch_prompt)
                    captions = parse_captions(raw, len(batch))
                    if captions is None:
                        print(f"  parse failure on batch {batch_no} "
                              f"(attempt {attempt}) — retrying", file=sys.stderr)
                        if attempt < args.max_retries:
                            time.sleep(max(2.0, args.sleep))
                        continue
                    break
                except Exception as e:  # rate limits, network blips, 5xx
                    wait = min(60, 5 * 2 ** (attempt - 1))
                    print(f"  API error (attempt {attempt}/{args.max_retries}): "
                          f"{type(e).__name__}: {e} — "
                          f"{'sleeping %ds' % wait if attempt < args.max_retries else 'giving up'}",
                          file=sys.stderr)
                    if attempt < args.max_retries:
                        time.sleep(wait)

            if captions is None:
                failed_batches += 1
                print(f"  batch starting at {batch[0].name} FAILED after retries — "
                      f"skipping (a re-run will pick these frames up)", file=sys.stderr)
                continue

            for path, cap in zip(batch, captions):
                idx = frame_index(path)
                record = {
                    "frame": path.name,
                    "video": video_src,
                    "t": offset + (idx - 1) * interval,
                    "t_rel": (idx - 1) * interval,
                    **cap,
                    "prompt_version": PROMPT_VERSION,
                    "provider": captioner.name,
                    "model": captioner.model,
                }
                out_f.write(json.dumps(record) + "\n")
                written += 1
            out_f.flush()

            elapsed_min = (time.time() - started) / 60
            rate = written / elapsed_min if elapsed_min > 0 else 0
            print(f"  {written}/{len(todo)} frames · {rate:.1f} frames/min")

    elapsed_min = (time.time() - started) / 60
    stats = {
        "run_frames": written,
        "elapsed_min": round(elapsed_min, 2),
        "frames_per_min": round(written / elapsed_min, 2) if elapsed_min > 0 else 0,
        "tokens_in": captioner.tokens_in,
        "tokens_out": captioner.tokens_out,
        "est_cost_usd": 0.0,  # free tier; update manually if paid credit is used
        "provider": captioner.name,
        "model": captioner.model,
        "prompt_version": PROMPT_VERSION,
        "failed_batches": failed_batches,
    }
    stats_path.write_text(json.dumps(stats, indent=2) + "\n")
    print(f"\nDone: {written} frames in {elapsed_min:.1f} min "
          f"({stats['frames_per_min']} frames/min) · "
          f"tokens in/out: {captioner.tokens_in}/{captioner.tokens_out}")
    if failed_batches:
        print(f"{failed_batches} batch(es) failed — re-run the same command to fill the gaps.")


if __name__ == "__main__":
    main()
