"""FilmFinder kill-test: THE Phase-1 gate.

Runs the 5 canonical queries as raw semantic search against the dev
collection, shows the top-3 moments per query, asks you to score each one
(is a correct moment in the top 3?), and writes KILLTEST.md.

Gate rule: >=4/5 -> proceed to Phase 2. 3/5 -> marginal, rescue path first.
<=2/5 -> STOP, escalate for a pivot ruling.

Usage:
    python killtest.py                      # interactive scoring
    python killtest.py --no-interactive     # just print results, no scorecard
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

EMBED_MODEL = "BAAI/bge-small-en-v1.5"

CANONICAL_QUERIES = [
    "corner kick",
    "goalkeeper save",
    "shot on goal",
    "throw-in",
    "celebration",
]


def mmss(t: float) -> str:
    t = int(t)
    if t >= 3600:
        return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"
    return f"{t // 60}:{t % 60:02d}"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--collection", default="filmfinder_dev")
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument("--no-interactive", action="store_true")
    ap.add_argument("--out", default="KILLTEST.md")
    args = ap.parse_args()

    load_dotenv()

    from fastembed import TextEmbedding
    from qdrant_client import QdrantClient

    url, api_key = os.environ.get("QDRANT_URL"), os.environ.get("QDRANT_API_KEY")
    if not url or not api_key:
        sys.exit("QDRANT_URL / QDRANT_API_KEY missing — fill .env first")
    client = QdrantClient(url=url, api_key=api_key, timeout=60)
    model = TextEmbedding(model_name=EMBED_MODEL)

    results_per_query = {}
    for q in CANONICAL_QUERIES:
        vec = list(model.query_embed(q))[0].tolist()
        hits = client.query_points(
            collection_name=args.collection,
            query=vec,
            limit=args.top_k,
            with_payload=True,
        ).points
        results_per_query[q] = hits
        print(f"\n=== \"{q}\" ===")
        for rank, h in enumerate(hits, 1):
            p = h.payload
            print(f"  {rank}. t={mmss(p['t'])} ({p['t']}s) · score={h.score:.3f} · "
                  f"action={p['action']} · {p['frame']}")
            print(f"     {p['description']}")

    if args.no_interactive:
        return

    print("\n--- Scoring: check each query's frames/video and answer honestly ---")
    scorecard = []
    for q in CANONICAL_QUERIES:
        ans = ""
        while ans not in ("y", "n"):
            ans = input(f"Correct moment in top {args.top_k} for \"{q}\"? [y/n] ").strip().lower()
        note = ""
        if ans == "n":
            note = input("  Miss note (what the VLM said vs. what was on screen): ").strip()
        scorecard.append({"query": q, "hit": ans == "y", "note": note})

    score = sum(1 for s in scorecard if s["hit"])
    stats = {}
    stats_path = Path("captions_dev_stats.json")  # written by captioner.py next to its --out
    if stats_path.exists():
        stats = json.loads(stats_path.read_text())

    if score >= 4:
        decision = f"**PASS ({score}/5)** — proceed to Phase 2."
    elif score == 3:
        decision = ("**MARGINAL (3/5)** — rescue path scheduled as Phase 2's first task: "
                    "caption-prompt iteration against the missed frames; consider CLIP dual vectors.")
    else:
        decision = (f"**FAIL ({score}/5)** — STOP. Escalate to the strategy agent "
                    "for a pivot ruling before any Phase 2 task.")

    lines = [
        "# Kill-Test Scorecard",
        "",
        f"- **Score: {score}/5** (correct moment in top {args.top_k})",
        f"- Collection: `{args.collection}`",
        f"- Captioning rate: {stats.get('frames_per_min', '?')} frames/min "
        f"({stats.get('provider', '?')} / {stats.get('model', '?')}, "
        f"prompt {stats.get('prompt_version', '?')})",
        f"- Cost: ${stats.get('est_cost_usd', 0.0)} "
        f"(tokens in/out: {stats.get('tokens_in', '?')}/{stats.get('tokens_out', '?')})",
        "",
        "| Query | Top-3 hit | Notes |",
        "|---|---|---|",
    ]
    for s in scorecard:
        lines.append(f"| {s['query']} | {'✅' if s['hit'] else '❌'} | {s['note']} |")
    lines += ["", "## Gate decision", "", decision, ""]

    Path(args.out).write_text("\n".join(lines))
    print(f"\nScore: {score}/5 → {decision}")
    print(f"Wrote {args.out} — commit it.")


if __name__ == "__main__":
    main()
