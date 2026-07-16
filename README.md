# FilmFinder ⚽🔍

**Ctrl+F for game film: type plain English, jump to the exact moment in match video.**

🔗 **Live demo:** https://filmfinder-3w3t24wvvcf7xsbgj32jhx.streamlit.app
🎬 **Demo video:** _TODO(Thu): ≤2-min video link_

**One-click tours** (every search + moment is a URL):
[a goal past the diving keeper](https://filmfinder-3w3t24wvvcf7xsbgj32jhx.streamlit.app/?q=goal&t=5224) ·
[when did the keeper mess up](https://filmfinder-3w3t24wvvcf7xsbgj32jhx.streamlit.app/?q=when+did+the+keeper+mess+up) ·
[players arguing with the referee](https://filmfinder-3w3t24wvvcf7xsbgj32jhx.streamlit.app/?q=players+arguing+with+the+referee) ·
[shots in the last 10 minutes of the first half](https://filmfinder-3w3t24wvvcf7xsbgj32jhx.streamlit.app/?q=shots+in+the+last+10+minutes+of+the+first+half)

## The problem

Coaches and analysts scrub through hours of footage to find seconds of signal —
every corner, every keeper error, every late-game push. Professional tools
(fixed taxonomies, human tagging queues) start at thousands per season.
FilmFinder gives grassroots teams the core capability for the price of a
YouTube link: search a match like a document, click, and the video jumps there.

## How it works

```
             BUILD TIME (once per match)                RUNTIME (every search, <1s)
┌──────────┐  ┌────────┐  ┌─────────────┐              ┌────────────────────────┐
│ match    │→ │ ffmpeg │→ │ Gemini VLM  │              │ "saves in the last     │
│ video    │  │ frames │  │ captions    │              │  10 minutes"           │
└──────────┘  │ (1/2s) │  │ action+desc │              └───────────┬────────────┘
              └────────┘  └──────┬──────┘                          ▼
                                 ▼                     ┌────────────────────────┐
                          ┌─────────────┐              │ query parser           │
                          │ FastEmbed   │              │ (Lyzr agent, python    │
                          │ 384-d       │              │  fallback)             │
                          └──────┬──────┘              └───────────┬────────────┘
                                 ▼                                 ▼
                          ┌─────────────────────────────────────────────────────┐
                          │ Qdrant: vector similarity + action/time payload     │
                          │ filters in ONE query (hybrid search)                │
                          └──────────────────────────┬──────────────────────────┘
                                                     ▼
                                     ┌────────────────────────────────┐
                                     │ 10s moment clustering → cards  │
                                     │ → YouTube player seeks to t−3s │
                                     └────────────────────────────────┘
```

- **Captions, not video embeddings, are the index.** A vision LLM watches each
  frame once and writes structured JSON (17-action taxonomy, description with
  jersey colors, zone, confidence). At query time no LLM ever touches a frame —
  that's why search is sub-second and hosting is free-tier.
- **Queries decompose into three signals**: a hard action filter
  (`saves → action=save`), a time window computed against the *measured*
  kickoff/halftime boundaries (`last 10 minutes → t ≥ 5675s`), and a semantic
  vector for everything else. Qdrant runs all three in one call.
- **Every timestamp in the UI is a measured video timestamp** — clicking a
  result seeks the official YouTube embed 3 seconds before the moment, so you
  see the buildup.

Beyond search, three things the index makes cheap:

- **Match Pulse** — a clickable timeline strip under the player drawing every
  indexed frame as an action-colored tick across the full 105 minutes; search
  results ignite as markers on it, and clicking one seeks the video there.
- **✨ More like this** — one click on any result finds the most similar
  moments in the match via Qdrant's Recommendation API (recommend by stored
  point ID: no query text, no re-embedding — click one corner routine, get
  that team's other corners).
- **📎 Clip board** — save moments across searches and export a session plan
  where every line is a timestamped `youtu.be` deep link a coach can paste
  straight into the team chat.

## Sponsor stack

| Tool | Role | Status |
|---|---|---|
| **Qdrant** | Structural backbone: hybrid retrieval (vectors + `action`/`t` payload indexes). The product does not exist without it. | Live |
| **Lyzr Studio** | Agent #1 parses long-tail phrasing into the retrieval contract ("when did the keeper mess up" → enriched semantic query). Agent #2 writes the Scout Note panel — a 2-3 bullet tactical summary of the retrieved moments. Both created programmatically via the v3 API, both behind flags (`USE_LYZR_PARSER`, `USE_LYZR_SCOUT`), both with plain-Python fallbacks: a Lyzr outage degrades capability, never availability. | Live behind flags |
| **Enkrypt AI** | `guardrails.py` guards the two trust seams — query-input sanitization (prompt-injection is stripped, flagged, and disclosed in the UI) and Scout-Note grounding validation (every bullet must cite a timestamp present in the retrieved set, or the note is discarded). Implemented as policy-shaped functions so the hosted Enkrypt equivalents can replace the bodies without touching call sites — an **Enkrypt-ready integration point**, honestly labeled: the seams are self-built today. | Enkrypt-ready |

The design rule throughout: **the deterministic core never depends on a
sponsor API being up.** Flags + fallbacks + a validation layer between every
agent and the UI.

## Hallucination policy

The only free text an LLM contributes at runtime is the Scout Note, and it
passes a code-enforced gate: bullets citing any timestamp not present in the
actual retrieved set are rejected wholesale, and a deterministic summarizer
(grounded by construction) takes over. Captions themselves carry per-frame
`confidence` and `prompt_version` for auditability.

## Quick start (dev)

```bash
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in your keys
python verify_keys.py       # every key verified with a real call
```

Full pipeline:

```bash
python extract_frames.py --video match01.mp4 --out frames/match01
python captioner.py --frames-dir frames/match01 --out captions_match01.jsonl
python indexer.py --captions captions_match01.jsonl --collection filmfinder_match01
python search.py "corner kick" --collection filmfinder_match01   # CLI sanity check
streamlit run app.py
```

## Measured accuracy (including the misses)

Full-match numbers, production config (Lyzr parser on), from the repeatable
harness ([qa_eval.py](qa_eval.py) → [eval_results.md](eval_results.md)):

- **12/12 scored queries hit at rank 1 (MRR 1.00)** across canonical,
  time-filter, compound-time, and long-tail categories.
- **1 expected miss, kept on the scoreboard**: "counterattack after losing
  the ball" — per-frame captions cannot see multi-frame transitions. Full
  manual log in [QA.md](QA.md).
- Methodology honesty: gold windows come from caption-level event extraction
  (independent of retrieval *ranking*, but bounded by caption quality) plus
  human-verified QA timestamps — it's a regression harness, not an unbiased
  recall estimate.
- The harness caught a real bug on its first run: the Lyzr parser agent did
  "last 10 minutes" arithmetic wrong (a 60-second window). Fix: the
  deterministic parser's exact time math now overrides the agent's whenever
  it recognizes a time phrase — LLMs keep the semantics, regex keeps the
  arithmetic.

## Honest limitations

- **One match indexed.** The pipeline is match-agnostic; the demo corpus isn't.
- **Teams are jersey colors, not names.** Captions say who is *near* the ball,
  not who *took* the kick — team attribution is approximate.
- **Recall is caption-bound.** If the VLM didn't write it, search can't find
  it. Frame sampling at 2s can miss ball-strike instants; multi-frame events
  (counterattacks) exceed a per-frame captioner's vocabulary.
- **The keyword parser reads literally.** Negation ("no goals") and
  contradictory compounds ("second half of the first half") parse to their
  dominant keywords; the Lyzr parser path handles more of these, but neither
  is a full language model of soccer talk.
- **Playback needs the YouTube embed** to stay public and embeddable.

## Roadmap

Self-hosted deployment (local Qdrant + local embedder + club-owned captions)
keeps youth-team footage on club hardware — nothing leaves the building except
the coach's queries. The open stack is the point: we built the hard part, not
rented it.

## Footage

AFC Bournemouth 4–3 Liverpool, official club channel, Creative Commons
Attribution — verified on access (2026-07-15). Details: [ATTRIBUTION.md](ATTRIBUTION.md).
