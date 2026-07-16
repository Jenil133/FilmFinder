"""Guardrails on FilmFinder's two trust seams (Enkrypt-ready integration point).

Seam 1 — query input: raw user text flows to an LLM agent (Lyzr parser) and an
embedder. sanitize_query() neutralizes prompt-injection material and abnormal
input before it reaches either.

Seam 2 — Scout Note output: agent-written bullets flow to the UI.
ground_bullets() enforces that every bullet cites a timestamp present in the
retrieved set — the hallucination gate for the only free-text the app renders.

Both functions are deliberately shaped like policy checks so a hosted
guardrails provider (Enkrypt AI) can replace the bodies without touching the
call sites: same inputs, same outputs, same raise-on-violation behavior.
"""

import re

MAX_QUERY_CHARS = 200
MAX_BULLETS = 3

# Characters a soccer search legitimately needs. Everything else (braces,
# backticks, angle brackets, escapes) is agent-confusion material, not soccer.
_ALLOWED = re.compile(r"[^a-zA-Z0-9\s'\-:,.?!/]")

# Instruction-override phrasing aimed at the parser agent, not the index.
_INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in (
        r"ignore\s+(?:all\s+|any\s+)?(?:previous|prior|above)\s+instructions?",
        r"disregard\s+(?:all\s+|any\s+)?(?:previous|prior|above)",
        r"\bsystem\s+prompt\b",
        r"\byou\s+are\s+now\b",
        r"\bnew\s+instructions?\s*:",
        r"\brespond\s+with\b.*\bjson\b",
        r"\breturn\s+exactly\b",
        r"\bact\s+as\b",
    )
]


def sanitize_query(query: str) -> tuple[str, bool]:
    """Raw query -> (clean query, flagged). Never raises, never blocks:
    a stripped query still searches, it just can't carry instructions."""
    flagged = False
    q = str(query)[:MAX_QUERY_CHARS]
    q = "".join(ch for ch in q if ch.isprintable() or ch.isspace())

    for pat in _INJECTION_PATTERNS:
        q, n = pat.subn(" ", q)
        if n:
            flagged = True

    cleaned = _ALLOWED.sub(" ", q)
    if cleaned != q:
        flagged = True
    cleaned = " ".join(cleaned.split())
    return cleaned, flagged


def ground_bullets(data: dict, valid_ts: set) -> list:
    """Validate agent-written Scout Note bullets against the retrieved set.

    Returns [{t, text}, ...] or raises ValueError — callers treat any raise
    as "discard the note", so nothing ungrounded can render.
    """
    bullets = data["bullets"]
    if not isinstance(bullets, list) or not 1 <= len(bullets) <= MAX_BULLETS:
        raise ValueError(f"bad bullet count: {bullets!r}")
    out = []
    for b in bullets:
        t = int(b["t"])
        if t not in valid_ts:
            raise ValueError(f"ungrounded citation t={t}")
        text = str(b["text"]).strip()
        if not 10 <= len(text) <= 250:
            raise ValueError(f"bad bullet text: {text!r}")
        out.append({"t": t, "text": text})
    return out
