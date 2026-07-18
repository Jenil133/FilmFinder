# Submission kit (draft Wed, finalize Thu)

## Portal fields

- **Project name:** FilmFinder
- **One-liner:** Ctrl+F for game film — search a soccer match in plain English, click, and the video jumps there.
- **Repo:** https://github.com/Jenil133/FilmFinder
- **Live demo:** https://filmfinder-3w3t24wvvcf7xsbgj32jhx.streamlit.app
- **Video:** _TODO(Thu): link_
- **Track:** Athlete Performance & Coaching

## Description (paste-ready, ~250 words)

Coaches scrub hours of footage to find seconds of signal — every corner,
every keeper error, every late-game push. Professional tagging tools cost
thousands per season and lock you into fixed taxonomies. FilmFinder gives
grassroots teams the core capability for the price of a YouTube link: type
what happened in plain English and the match video jumps to that moment.

The trick is treating video search as a text problem. A vision LLM watches
the match once, offline, writing structured captions per frame (17-action
taxonomy, jersey colors, zone, confidence). FastEmbed vectors plus those
fields land in Qdrant, whose hybrid search fuses semantic similarity with
hard action and time filters in one query — "saves in the last 10 minutes"
becomes a vector plus `action=save` plus `t≥5675s` against measured kickoff
and halftime boundaries. No LLM touches a frame at query time, so search is
sub-second on a free-tier stack. The whole match renders as a clickable
Match Pulse timeline where results ignite as markers; one click on any
result finds similar moments via Qdrant's Recommendation API (search by a
frame's own stored vector — no typing); saved clips export as a session
plan of timestamped video links.

Two Lyzr agents extend the core behind flags with plain-Python fallbacks: a
query parser for long-tail phrasing and a Scout Note whose every bullet must
cite a retrieved timestamp or it doesn't render. A repeatable eval harness
scores 12/12 queries at rank 1 (MRR 1.00) — and caught a real agent
arithmetic bug on its first run. The one known miss (counterattacks) stays
on the scoreboard: honest limitations are documented, not hidden.

## Demo video script (≤2:00, screen recording + voiceover)

| Clock | Shot | Voiceover beat |
|---|---|---|
| 0:00–0:12 | Deployed app: player + the Match Pulse strip idle below it | "This is FilmFinder — Ctrl+F for game film. One full Premier League match indexed. That strip is the whole match, every moment color-coded." |
| 0:12–0:35 | Type **"corner kick"** → six red markers ignite on the strip → click a marker → video seeks, corner plays | "Type what happened, and watch it light up across 105 minutes. Click a marker — the video jumps there, three seconds early so you see the buildup." |
| 0:35–0:55 | Type **"saves in the last 10 minutes of the first half"** → point at the filter caption | "Not just keywords: action filters plus time windows computed off the real match clock, fused with semantic vectors in one Qdrant query." |
| 0:55–1:15 | Type **"when did the keeper mess up"** → results + Scout Note panel | "Long-tail phrasing goes through a Lyzr agent. The Scout Note is grounded — every bullet must cite a retrieved timestamp, enforced in code, or it doesn't render." |
| 1:15–1:35 | Click **✨ More like this** on a corner card → same team's other corners appear | "One click, no typing — Qdrant's Recommendation API searches by the moment's own stored vector. Click one corner routine, get their whole set-piece pattern." |
| 1:35–1:50 | **➕ Save clip** twice → sidebar → **Export session plan** → show the .md with youtu.be links | "Save what matters, export a session plan — every line a timestamped link a coach pastes into the team chat." |
| 1:50–2:00 | README limitations section on screen | "One match, jersey-color team IDs, caption-bound recall — the README tells the truth. Four days, free stack: Qdrant, Lyzr, Gemini, Streamlit." |

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
  transitions). Full match: 12/12 gold queries at rank 1 (MRR 1.00, hit@6
  12/12) via the repeatable harness (`python qa_eval.py`); earlier manual
  pass 9/10 with the counterattack miss documented.
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

## Thursday runbook — status

1. ~~Captions 3138~~ ✅  2. ~~Index top-up~~ ✅  3. ~~App swap~~ ✅
4. ~~Streamlit secrets~~ ✅  5. ~~Deploy + QA.md + README numbers~~ ✅
6. ~~Commit captions~~ ✅
7. **Record video per script → upload → drop link here + README** ← YOU
8. **Portal: paste description, verify all fields, submit** ← YOU

Frozen build: `93fc82d`. Hard-refresh any old tab before demoing.
