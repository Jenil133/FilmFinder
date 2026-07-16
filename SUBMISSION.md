# Submission kit (draft Wed, finalize Thu)

## Portal fields

- **Project name:** FilmFinder
- **One-liner:** Ctrl+F for game film — search a soccer match in plain English, click, and the video jumps there.
- **Repo:** https://github.com/Jenil133/FilmFinder
- **Live demo:** https://filmfinder-3w3t24wvvcf7xsbgj32jhx.streamlit.app
- **Video:** _TODO(Thu): link_
- **Track:** _TODO(Thu): confirm exact track name in portal_

## Description (paste-ready, ~230 words)

Coaches and analysts scrub hours of footage to find seconds of signal — every
corner, every keeper error, every late-game push. Professional tagging tools
cost thousands per season and lock you into fixed taxonomies. FilmFinder gives
grassroots teams the core capability for the price of a YouTube link: type
what happened in plain English, and the match video jumps to that moment.

The trick is treating video search as a text problem. A vision LLM watches the
match once, offline, writing structured captions per frame (17-action
taxonomy, jersey colors, field zone, confidence). FastEmbed vectors plus those
structured fields land in Qdrant, whose hybrid search fuses semantic
similarity with hard action and time filters in a single query — "saves in the
last 10 minutes" becomes a vector plus `action=save` plus `t≥5675s` against
measured kickoff and halftime boundaries. At query time no LLM touches a
frame, so search is sub-second on an entirely free-tier stack.

Two Lyzr agents extend the core behind feature flags with plain-Python
fallbacks: a query-parser that handles long-tail phrasing ("when did the
keeper mess up"), and a Scout Note that summarizes retrieved moments — gated
by code that rejects any bullet citing a timestamp not actually retrieved.
Guardrails sanitize query input on the way in (Enkrypt-ready seams). One full
Premier League match (CC-BY footage) is indexed and searchable in the live
demo, with measured accuracy — including the misses — documented in the repo.

## Demo video script (≤2:00, screen recording + voiceover)

| Clock | Shot | Voiceover beat |
|---|---|---|
| 0:00–0:15 | Deployed app, cursor idle on search bar | "This is FilmFinder — Ctrl+F for game film. One full Premier League match indexed. Watch." |
| 0:15–0:40 | Type **"corner kick"** → results appear → click a jump button → video seeks, corner plays | "Type what happened. Click. The video jumps there — three seconds early so you see the buildup." |
| 0:40–1:05 | Type **"saves in the last 10 minutes of the first half"** → point at the filter caption | "It's not just keywords. Action filters and time windows computed off the real match clock, fused with semantic search in one Qdrant query." |
| 1:05–1:30 | Type **"when did the keeper mess up"** → results + Scout Note panel | "Long-tail phrasing goes through a Lyzr agent. And this Scout Note is grounded — every bullet must cite a retrieved timestamp, enforced in code, or it doesn't render." |
| 1:30–1:45 | Click **🎲 Surprise me** → whatever lands | "Everything degrades gracefully — agents behind flags, fallbacks everywhere. Judges: try to break it." |
| 1:45–2:00 | README limitations section on screen | "One match, jersey-color team IDs, caption-bound recall — the README tells the truth. Built in four days on a free stack: Qdrant, Lyzr, Gemini, Streamlit." |

Recording notes: 1080p, hide bookmarks bar, mute mic pops, do a full dry run
first — the first search after deploy is slower (model warm-up), so warm the
app before recording.

## Q&A crib sheet

- **"How is this different from Hudl?"** — Hudl is fixed taxonomy + human
  tagging queues + enterprise pricing. FilmFinder is open-vocabulary and
  instant: the caption index answers phrasings nobody pre-tagged, on free
  infrastructure a volunteer coach can run.
- **"Why not Twelve Labs / a video-embedding API?"** — Those rent you the hard
  part. This stack is open and self-hostable end to end (local Qdrant, local
  embedder, own captions) — that matters for the privacy roadmap and for a
  grassroots budget. We built the retrieval engine, not a wrapper.
- **"What's your accuracy?"** — Quote QA.md numbers, misses first: the
  counterattack query is an honest failure (per-frame captions can't see
  transitions). 5/5 canonical queries at rank 1 on the dev slice;
  _TODO(Thu): full-match numbers_.
- **"Hallucinations?"** — The only runtime LLM free-text is the Scout Note,
  and it passes a code gate: cite a timestamp outside the retrieved set and
  the note is discarded. Captions carry confidence + prompt version for audit.
- **"Youth-team privacy?"** — Demo uses licensed public footage (CC-BY,
  attribution in repo). The roadmap is self-hosted: club footage never leaves
  club hardware; only queries move.
- **"What broke along the way?"** — Gemini's 500 req/day cap mid-run (solved:
  resumable JSONL cache + quota-reset scheduling), Groq's 3-image/8k-TPM
  vision limits (solved: fallback demoted to gap-filler), Lyzr's create API
  silently dropping system_prompt (solved: agent_role/instructions fields).
  The resume drill — kill the captioner mid-run, relaunch, zero duplicates —
  is in the repo history.

## Thursday runbook (gated on tonight's captions)

1. `wc -l captions_match01.jsonl` → expect 3138 (log: run_midnight.log)
2. `python indexer.py --captions captions_match01.jsonl --collection filmfinder_match01` (top-up, idempotent)
3. app.py: `COLLECTION = "filmfinder_match01"`, `THUMBS_DIR = .../thumbs/match01`
4. Streamlit Cloud secrets (user): `LYZR_API_KEY`, `USE_LYZR_PARSER="1"`, `USE_LYZR_SCOUT="1"`
5. Push → verify deployed app cold-start → full-match QA (10 queries) → QA.md + README numbers
6. Commit completed captions_match01.jsonl + stats
7. Record video per script → upload → drop links here and in README
8. Portal: paste description, verify all fields, submit
