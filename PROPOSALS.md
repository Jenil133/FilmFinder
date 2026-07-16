# PROPOSALS — additions before Thursday night

*How this list was made: 5 ideation passes over the real repo (demo theater,
sponsor-prize depth, retrieval quality, Friday reliability, coach value) →
30 proposals → each adversarially verified against the actual code, quotas,
and clock. 27 survived, 2 were killed on evidence (see bottom). The top idea
was proven live against our Qdrant collection before making this list.*

**Budget reality:** tonight ≤ 2.5 focused hours · Thursday ≈ 5–6 hours AFTER
the sacred 3-hour runbook · Friday is rehearsal only. Everything below is
behind a flag or purely additive; nothing touches the MVP path.

---

## ⚠️ Tier 0 — do regardless (found during verification)

### 0. ✅ SHIPPED (Wed night, commit bf4a0cc) — Lyzr credit leak fix: circuit breaker + memoization
Streamlit reruns the entire script on every widget interaction. Today **every
"Jump to" click re-executes `run_search` AND `scout_note` for the same query —
2 Lyzr credits per seek click** with flags on, from a ~20-credit monthly pool.
Judges clicking around Friday would drain it in minutes, and once credits die,
every search eats the 6s parser timeout + 8s scout timeout before falling back.

- **Fix:** `lyzr_guard.py` — (a) `functools.lru_cache` memo on the parser call
  and a `(query, moment-ts)`-keyed `st.cache_data` on the scout note, so
  repeat executions are free; (b) a circuit breaker: 2–3 consecutive Lyzr
  failures → skip Lyzr entirely for 10 min (no timeout tax), half-open retry
  after.
- **Safety:** only active when the Lyzr flags are already on; breaker can only
  ever *skip* into the already-QA'd fallback.
- Verifier confirmed the exact seams: `search.py` `parse_query_flagged`
  try/except and `scout_note.scout_note` try/except.

---

## Tier 1 — recommended plan (in order)

### 1. ✅ SHIPPED (Thu 01:15 AM, commit ee1fb38) — "More like this" — Qdrant Recommendation API
One button per result card: click a corner kick, instantly get every other
corner routine in the match — no typing. Uses Qdrant's **Recommendation API**
(`RecommendQuery`, recommend-by-stored-point-ID), a differentiator feature most
hackathon teams never touch → strongest single Qdrant-prize move available.

- **Proven live during verification:** from a corner at t=4721 it returned the
  other corners at 0.83–0.91 similarity against our real collection.
- Verifier corrections baked in: add `point_id: str(rep.id)` in
  `cluster_moments`; namespace similar-row button keys (`simjump_{t}`) to avoid
  StreamlitDuplicateElementKey; clear `st.session_state.similar_to` when the
  query changes; exclude hits inside the source moment's ±10s window; pass the
  `COLLECTION` constant so Thursday's swap keeps working; **omit `using=`**
  (our collection is single unnamed vector).
- **Safety:** invisible until clicked; same try/except pattern as `run_search`.

### 2. Match Pulse — clickable full-match timeline strip — **3h hard box · Thursday · demo centerpiece**
A strip under the player plotting all ~3.1k indexed frames by time, colored by
action; search results ignite as large markers on it. Judge types "corner
kick" and watches dots light up along 105 minutes of match — the invisible
index becomes a visible artifact. Doubles as an honesty display (open_play
visibly dominates, matching the README).

- **Use Altair, not Plotly** (verifier: ships with Streamlit → zero
  requirements change → no risky Cloud dependency rebuild near the deadline).
- Data via one cached Qdrant `scroll` (`t`,`action` only, ~4 pages, <1s).
- Click-to-seek via the chart selection callback (same `on_click` pattern as
  the jump buttons); **requires Tier 0 first** or every strip click burns
  credits.
- **Safety:** `SHOW_TIMELINE` flag, whole render in try/except; degrades to
  display-only if selection events misbehave on Cloud.

### 3. Keep-alive pinger + real inference warmup — **1h · Thursday**
GitHub Actions cron curls the app every 10 min from Thursday evening through
Friday noon so Community Cloud never sleeps, plus one dummy
`query_embed('warmup')` + `get_collection()` inside `engine()` so the first
judge search pays ~0s extra. Kills the classic hackathon demo-killer.
- Verifier: marginal warmup win is ~0.3–1s (ONNX session already built in the
  constructor) — still worth one line; the cron is the real win.

### 4. Clip board + session-plan export — **2.5h · Thursday stretch (first to cut)**
"➕ Save" on each card collects moments in the sidebar; one click downloads a
session plan (Markdown/CSV) where every line is `mm:ss · action · description ·
https://youtu.be/{id}?t={s}` deep link. This is literally how grassroots
coaches share film — the strongest "real product, not a demo" signal.
- **Requires Tier 0 first** (each save click would otherwise burn 2 credits).
- **Safety:** pure session-state UI; export omits links if VIDEO_ID missing.

**Tier 1 total: ~8h against ~8 available → fits with the kill order: cut #4,
then #3, then shrink #2 to display-only.**

---

## Tier 2 — take if the day goes well / conditions land

| Idea | Hours | Condition / note |
|---|---|---|
| **Live Enkrypt on the query seam** | 3 | Only if free-tier key validates in a 15-min timebox. `guardrails.py` was built as the exact swap point; verified API shape (`POST /guardrails/detect`, `apikey` header). Turns the sanitize step into a demo moment: type an injection, watch the shield banner. Promotes past Tier 1 #4 if sponsor prizes require live usage. |
| **Match Overview dashboard** | 3 | Event counts per half as clickable stats. Verifier ran the merge on real captions: corners 15 (11/4), shots 27, saves 18 — plausible; but goals=8 from replay mislabels → curate to ~6 safe actions, label goals "goal moments". |
| **Shareable deep links** (`?q=&t=`) | 2.5 | Hand judges a URL that opens mid-save at 41:07. Inbound `q` already passes through sanitize_query. |
| **X-ray mode** | 2.5 | Sidebar toggle exposing parsed contract, live Qdrant filter, ms latency badges, score bars. Technical-judge catnip. Needs Tier 0 first. |
| **Gold-labeled eval harness** | 2.5 | 20–25 hand-labeled queries → Recall@6/MRR table in README. Strengthens the honesty story; label gold windows only after tonight's full captions. |
| **Local-video offline mode** | 1.5 | `LOCAL_VIDEO_PATH` flag → zero-internet Friday contingency. Verifier: serve via `http.server`, never pass the 903MB file to `st.video` (it SHA-hashes the whole file per rerun). |

## Tier 3 — declined for this deadline (with reasons)

- **Hybrid BM25+dense RRF (Qdrant Query API)** — 3.5h and fully verified
  feasible (fastembed BM25 smoke-tested), but it means a parallel collection +
  reindex + re-QA within 24h of submission. Right feature, wrong week. Noted
  in README roadmap instead.
- **Play-window sequence documents** (searchable counterattacks) — 5h, medium
  risk; the honest fix for our #1 known weakness, but verification found the
  possession-flip heuristics need per-match color aliasing — not a Thursday
  job. Roadmap.
- **Instant highlight reel** — 5h, medium; YouTube iframe auto-advance is
  fragile under autoplay policies. "Clip board" delivers the coach value at
  half the cost.
- **"What led to this" context strip** — 3h; good, but overlaps More-like-this
  demo value; verifier found the single-scroll design needs a `should`-filter
  rewrite. Next-week feature.
- **CLIP image vectors** — 5–6h, high risk, invisible unless the eval demands
  it. Roadmap.
- Multi-match selector, local Qdrant mirror, precomputed demo cache, query
  expansion, cluster rescoring, smoke.py — all fine ideas, all below the
  demo-value-per-hour cut line.

## Killed by adversarial verification (documented so we don't re-litigate)

1. **Server-side moment dedup via Qdrant grouping API** — the build-time
  `segment_id` assignment breaks on out-of-order gaps; would have shipped
  subtle wrong grouping.
2. **Team-scoped search ("the red team's corners")** — verifier tested against
  real captions: `"red"` matches 78% of frames (both kits contain red).
  Would have demoed confidently wrong results — the worst failure mode.

---

## Decision needed from you

1. Approve Tier 0 + Tier 1 as the plan? (I start with Tier 0 + "More like
   this" tonight.)
2. Enkrypt: want me to attempt the free-tier signup validation (15-min box)
   tomorrow, or stay with the stub?
3. Any Tier 2 item you'd promote because it excites you personally? The demo
   is better when the demoer loves the feature.
