# Overnight/morning autonomous plan (Jul 16, from 3:00 AM PT)

Executed by scheduled Claude sessions every 2h while the user sleeps.
User-approved scope: this file + PROPOSALS.md Tier 1. Nothing else.

## Lock protocol (prevents overlapping runs)
At start: read OVERNIGHT_LOG.md. If its last line is `RUNNING <ISO time>` less
than 3h old → exit immediately (another run is active). Otherwise append
`RUNNING <now>`. At end of the run append `DONE <now> — <one-line summary>`.

## Hard rules
- Commit author: Jenil133 only. No Claude co-author line. Push to origin main.
- Never touch .env beyond reading. Never delete files or rewrite git history.
- No new external services. Existing APIs only (Gemini, Qdrant, Lyzr, GitHub).
- NEVER do the user-only items: Streamlit Cloud secrets, demo video, hackathon
  portal submission, anything on studio.lyzr.ai, purchases/signups of any kind.
- On quota/API errors: rely on the existing fallback patterns, log it, move on.
- Each run appends a short progress note to OVERNIGHT_LOG.md.
- MVP is sacred: new features behind flags exactly as PROPOSALS.md specifies;
  run the test batteries before every commit (venv/bin/python, py_compile +
  the patterns used in repo history).

## Steps, in order (skip anything already done — check git log and file state)

1. **Captions**: `wc -l captions_match01.jsonl` — target 3138 (log:
   run_midnight.log). Still growing → log + exit (next run rechecks).
   Stalled/dead after 3:10 AM → relaunch
   `nohup caffeinate -is venv/bin/python captioner.py --frames-dir frames/match01 --out captions_match01.jsonl --sleep 3 > run_gemini_retry.log 2>&1 &`
   then exit.
2. **Index top-up**: `venv/bin/python indexer.py --captions captions_match01.jsonl --collection filmfinder_match01`
   (idempotent). Then commit captions_match01.jsonl + captions_match01_stats.json.
3. **QA.md**: run the 10 queries from SUBMISSION.md's runbook spirit (5 chips +
   compound-time + long-tail + a known-miss like "counterattack") via
   `venv/bin/python search.py "<q>" --collection filmfinder_match01`; write
   honest results (hits at rank, misses included) into QA.md. Commit.
4. **App swap**: app.py `COLLECTION = "filmfinder_match01"`,
   `THUMBS_DIR = Path(__file__).parent / "thumbs/match01"`. Verify via
   search.py CLI + a local streamlit smoke if feasible. Commit + push
   (Cloud auto-deploys; Lyzr flags stay off there until the user adds secrets —
   expected, fine).
5. **PROPOSALS.md Tier 1**, strictly in order, one commit per feature, each
   with its verifier corrections applied and tests passing:
   a. "More like this" (Qdrant Recommendation API) — 2.5h box
   b. Match Pulse timeline — Altair only, SHOW_TIMELINE flag — 3h HARD box;
      if the box expires, ship display-only or revert cleanly
   c. Keep-alive: .github/workflows/keepalive.yml (cron */10, Thu 18:00 →
      Fri 20:00 UTC window) + engine() warmup line — 1h
   d. Clip board + export — 2.5h, only if all above are green
6. Update SUBMISSION.md checkboxes + leave a morning summary at the top of
   OVERNIGHT_LOG.md: what shipped, what's pending, what needs the user.

## Stop conditions
All steps done, or blocked on a user-only item, or two consecutive failures of
the same step (log it and stop touching that step).
