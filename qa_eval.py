"""Retrieval regression harness.

Methodology (stated so nobody over-reads the numbers): gold windows come from
two sources — (a) caption-level event extraction (stats.match_events), which
is independent of the retrieval RANKING but bounded by caption quality, and
(b) human-verified timestamps from the manual QA passes in QA.md. This is a
REGRESSION harness with an honest category breakdown, not an unbiased recall
estimate; that would require full manual video scrubbing.

Metrics per query: hit@1 / hit@6 (any of top-1/top-6 moments overlaps a gold
window ±TOLERANCE_S) and reciprocal rank of the first hit. Queries flagged
expected_miss document known limitations and don't count against the score
(they count FOR honesty).

Usage:
    python qa_eval.py --collection filmfinder_match01 [--write eval_results.md]
"""

import argparse
import json
from pathlib import Path

from search import find_moments, mmss

TOLERANCE_S = 15
GOLD_PATH = Path(__file__).parent / "gold_qa.jsonl"


def overlaps(m, windows, tol=TOLERANCE_S):
    lo, hi = m["start_t"] - tol, m["end_t"] + tol
    return any(not (g_hi < lo or g_lo > hi) for g_lo, g_hi in windows)


def evaluate(collection: str):
    rows = []
    with GOLD_PATH.open() as f:
        cases = [json.loads(line) for line in f if line.strip()]
    for case in cases:
        _, moments = find_moments(case["query"], collection=collection)
        rank = next((i for i, m in enumerate(moments, 1)
                     if overlaps(m, case["gold"])), None)
        rows.append({
            "query": case["query"],
            "category": case["category"],
            "expected_miss": case.get("expected_miss", False),
            "rank": rank,
            "hit1": rank == 1,
            "hit6": rank is not None,
            "rr": (1.0 / rank) if rank else 0.0,
            "top1": mmss(moments[0]["t"]) if moments else "-",
        })
    return rows


def render(rows) -> str:
    scored = [r for r in rows if not r["expected_miss"]]
    lines = ["# Retrieval eval (regression harness — see qa_eval.py header "
             "for methodology)", ""]
    lines.append(f"**Scored queries: {len(scored)}** · "
                 f"hit@1 {sum(r['hit1'] for r in scored)}/{len(scored)} · "
                 f"hit@6 {sum(r['hit6'] for r in scored)}/{len(scored)} · "
                 f"MRR {sum(r['rr'] for r in scored) / len(scored):.2f}")
    lines.append("")
    lines.append("| query | category | first hit rank | top-1 at |")
    lines.append("|---|---|---|---|")
    for r in rows:
        tag = " *(expected miss — documented limitation)*" if r["expected_miss"] else ""
        rank = r["rank"] if r["rank"] else "—"
        lines.append(f"| {r['query']}{tag} | {r['category']} | {rank} | {r['top1']} |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--collection", default="filmfinder_match01")
    ap.add_argument("--write", help="also write the markdown table to this path")
    args = ap.parse_args()

    rows = evaluate(args.collection)
    out = render(rows)
    print(out)
    if args.write:
        Path(args.write).write_text(out)
        print(f"written to {args.write}")


if __name__ == "__main__":
    main()
