# QA Log

Started Wednesday (Phase 2, dev index) — finished Thursday (Phase 3, full match).

## Phase 2 sanity suite — dev index (`filmfinder_dev`, 360 frames, match 69'–81')

Full runtime path (parse → hybrid retrieval → 10s clustering), top moments eyeballed.

### Canonical queries (all 5: correct moment at rank 1) ✅

| Query | Rank-1 moment | Notes |
|---|---|---|
| corner kick | 76:03 corner prep, 3-frame cluster | second moment is an 11-frame corner sequence |
| goalkeeper save | 85:09 keeper save cluster | known caption quirk: post-concede keeper frames can label "save" (see KILLTEST.md) |
| shot on goal | 87:03 strike from edge of box | |
| throw-in | 75:25 textbook throw-in stance | |
| celebration | 75:49 goalscorer running | ranks 2–3 are the 3–3 bench/crowd eruption, 5-frame cluster |

### Long-tail probes (no action filter — pure caption semantics)

| Query | Result | Verdict |
|---|---|---|
| counterattack after we lost the ball | possession challenge (tackle) + ball in flight | plausible but not a true counterattack — captions describe single frames, transitions across frames are invisible to them. Demo-curate around this. |
| players arguing with the referee | referee gesturing during stoppage; ref + player over a downed opponent | strong hit — jersey-color + referee vocabulary in captions carries it |
| the red team's corners | rank 2 = red-team corner prep; rank 1 = contested corner ball (both teams) | good; team-attribution via colors works but isn't precise — captions say who's *near* the ball, not who *took* the kick |

### Time filters (measured behavior, not aspiration)

- "corners in the second half" → Qdrant filter `action=corner AND t >= 3085` (verified in debug output); returns the expected corners.
- "corners in the first half" → `t <= 2900` correctly returns **nothing** on the
  second-half-only dev slice (no false hits; the semantic fallback also respects
  the time filter).
- Boundaries are *measured from the scoreboard clock*, not assumed: kickoff at
  video t=113, first half ends ≈2900, second half restarts at 3085 (the naive
  t=2700 split would mislabel ~6 minutes of footage).

## Observations feeding Thursday's decisions

1. Long-tail quality is good enough that the CLIP dual-vector upgrade looks
   unnecessary — re-evaluate after full-match QA.
2. Team-attribution queries ("the red team's X") work by color mention, so demo
   phrasing should use jersey colors, not team names.
3. Multi-frame *transition* concepts (counterattacks, build-up play) are the
   weakest query class — curate chips/demo away from them; candidate for the
   README limitations section.
