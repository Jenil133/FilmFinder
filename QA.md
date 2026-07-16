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

## Phase 3 full-match QA — `filmfinder_match01` (3,138 frames, full 105-min video)

Run Thursday 00:45 AM, production config (Lyzr parser flag ON — `parser: lyzr`
confirmed on all 10 parses). **9/10 queries return a correct moment at rank 1.**
The miss is the documented per-frame limitation, not a regression.

| # | Query | Rank-1 result | Verdict |
|---|---|---|---|
| 1 | corner kick | 1:16:04 red-black corner prep at the flag | ✅ (3 distinct corners in top 3) |
| 2 | goalkeeper save | 1:22:40 grey keeper ground save | ✅ |
| 3 | shot on goal | 1:14:12 yellow shooting motion toward goal | ✅ |
| 4 | throw-in | 1:32:26 yellow throw-in stance, linesman watching | ✅ |
| 5 | goal celebration | 1:24:30 red-black celebration — **4s after the 1:24:26 goal** (internally consistent) | ✅ |
| 6 | shots in the last 10 minutes of the first half | 45:14 shot (t=2714, inside the computed [2300, 2900] window) | ✅ compound time phrase honored; only 1 hit — honest, not padded |
| 7 | goals in the second half | 1:10:14 ball in net; ranks 2–3 are two more actual goals | ✅ all hits ≥ t=3085 |
| 8 | players arguing with the referee | 38:20 player literally arguing with the referee | ✅ long-tail semantic |
| 9 | when did the keeper mess up | 1:27:04 keeper dives, ball enters net (Lyzr enriched → "goalkeeper mistake error fumble") | ✅ conceded goals ranked 1–3 |
| 10 | counterattack after losing the ball | corner-kick ball in flight; rank 2 is a loose-ball scramble (semi-relevant) | ❌ **known miss** — per-frame captions cannot see multi-frame transitions |

Notes:
- Time boundaries validated end-to-end on the full video: kickoff t=113,
  halftime 2900→3085 (measured, not assumed).
- Recall is bounded by caption quality: "goal" labels include some replays,
  but clustering + score ranking kept real goals on top in every goal query.

## Observations feeding Thursday's decisions

1. Long-tail quality is good enough that the CLIP dual-vector upgrade looks
   unnecessary — re-evaluate after full-match QA.
2. Team-attribution queries ("the red team's X") work by color mention, so demo
   phrasing should use jersey colors, not team names.
3. Multi-frame *transition* concepts (counterattacks, build-up play) are the
   weakest query class — curate chips/demo away from them; candidate for the
   README limitations section.
