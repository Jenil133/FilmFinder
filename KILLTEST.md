# Kill-Test Scorecard — Phase 1 Gate

**Date:** 2026-07-15 (night of Tue Jul 14 → Wed Jul 15)
**Slice:** AFC Bournemouth 4–3 Liverpool, video 4525s–5245s (match clock ~69'–81'),
360 frames @ 1 per 2 s, 768 px. Contains Wilson's penalty aftermath, Fraser 76',
Cook 78' (3–3), celebrations, corners, saves, throw-ins.
**Collection:** `filmfinder_dev` (Qdrant Cloud, 360 points, bge-small-en-v1.5, cosine)
**Scoring:** each query hits if a correct moment is in the top 3 (verified by
looking at the actual frames, not just the captions).

- ## **Score: 5/5** ✅

| Query | Top-3 hit | Notes |
|---|---|---|
| corner kick | ✅ | ranks 1–2: player at the corner flag preparing the kick (69:39) |
| goalkeeper save | ✅ | rank 1 (78:45) was actually the keeper just after *conceding* the 3–3 — VLM labeled it "save"; rank 2 (80:29) is a genuine shot→save sequence, confirmed against adjacent frames |
| shot on goal | ✅ | rank 1: striker mid-shot at edge of box, keeper set (80:39) |
| throw-in | ✅ | rank 1: textbook throw-in stance (69:01); rank 3 was a throw-in the VLM labeled `open_play` — pure semantic search recovered it anyway |
| celebration | ✅ | rank 1 weak (goalscorer from behind, low visual evidence); ranks 2–3: bench + crowd erupting seconds after the 3–3 equalizer (78:53) |

## Measured numbers (feed Phase 2's overnight ETA)

- **Captioning rate: 38.0 frames/min** (gemini-3.1-flash-lite, 5-frame batches, 5 s pacing)
  → full match ~2,700 frames ≈ **75 min** (fits overnight with huge margin, even at half speed)
- **Cost: $0.00** (free tier; ~352k tokens in / ~22k out for the 295-frame run)
- Captions are mixed-provider: 65 frames on `gemini-3.5-flash` + 295 on
  `gemini-3.1-flash-lite` (see quota notes) — no visible quality difference.

## Free-tier quota discoveries (they rewrote the provider plan)

| Provider/model | Free-tier limit found | Consequence |
|---|---|---|
| gemini-3.5-flash | **20 requests/DAY** (429 mid-run) | unusable as primary |
| gemini-2.5-flash | 404 "no longer available to new users" | dead for new keys |
| Groq llama-4-scout | model shut down 07/17/26 | replaced by qwen3.6-27b |
| Groq qwen3.6-27b | max **3 images/request** (docs claim 5) + **8k tokens/min** (one 768px 3-image batch ≈ 9.7k tokens → doesn't fit) | emergency fallback only; would need ~448px frames |
| **gemini-3.1-flash-lite** | handled 59 requests in 7.8 min without throttling | **new primary captioner** |

## Reliability drills

- **Resume drill: PASS** — re-running the captioner on the completed set added
  **zero** new/changed JSONL lines (byte-identical file).
- Mid-run provider death (Gemini 429 at frame 65) was recovered by resuming
  with a different provider against the same cache — the mechanism Phase 2's
  overnight run depends on is proven under a real failure, not a simulated one.

## Gate decision

**PASS (5/5) — proceed to Phase 2 as written.** No rescue path needed.
Known quality notes for Phase 2: "save" captions can fire on post-concede
keeper shots (near-miss tonight); celebration rank-1 was low-evidence. Both are
caption-prompt iteration candidates if long-tail QA disappoints, not blockers.
