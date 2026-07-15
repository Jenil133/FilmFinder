"""Lyzr agent #2: Scout Note (stretch tier 2).

Turns the retrieved moments into a 2-3 bullet tactical summary rendered above
the results. The grounding rule is enforced HERE, in code, not trusted to the
agent: every bullet must cite a timestamp present in the retrieved set, or
the agent's note is discarded and the deterministic local summarizer (which
is grounded by construction) takes over. The panel can never show a claim
about a moment that wasn't actually retrieved.

Panel appears only when USE_LYZR_SCOUT is on; the Lyzr call failing (timeout,
quota, bad JSON) downgrades to the local note, never to an error.
"""

import json
import os
import re
import uuid

import requests

LYZR_CHAT_URL = "https://agent-prod.studio.lyzr.ai/v3/inference/chat/"
DEFAULT_AGENT_ID = "6a5803d34f3fc59d564a6764"
TIMEOUT_S = 8.0
MAX_BULLETS = 3


def mmss(t: float) -> str:
    t = int(t)
    if t >= 3600:
        return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"
    return f"{t // 60}:{t % 60:02d}"


def scout_note(query: str, moments: list) -> dict | None:
    """Moments in, note out: {"bullets": [{t, time, text}], "source": str} | None.

    None means "render no panel" (flag off or nothing to summarize).
    """
    if not moments:
        return None
    if os.environ.get("USE_LYZR_SCOUT", "").lower() not in ("1", "true", "yes"):
        return None
    try:
        return _lyzr_note(query, moments)
    except Exception:
        return _local_note(moments)


def _lyzr_note(query: str, moments: list) -> dict:
    payload = {
        "query": query,
        "moments": [{"t": m["t"], "time": mmss(m["t"]), "action": m["action"],
                     "description": m["description"]} for m in moments],
    }
    resp = requests.post(
        LYZR_CHAT_URL,
        headers={"x-api-key": os.environ["LYZR_API_KEY"],
                 "Content-Type": "application/json"},
        json={
            "user_id": os.environ.get("LYZR_USER_ID", "filmfinder-app"),
            "agent_id": os.environ.get("LYZR_SCOUT_AGENT_ID", DEFAULT_AGENT_ID),
            "session_id": f"ffs-{uuid.uuid4().hex[:12]}",
            "message": json.dumps(payload),
        },
        timeout=TIMEOUT_S,
    )
    resp.raise_for_status()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp.json()["response"].strip())
    data = json.loads(text)

    # The hard rule: every cited t must exist in the retrieved set.
    valid_ts = {int(m["t"]) for m in moments}
    bullets = data["bullets"]
    if not isinstance(bullets, list) or not 1 <= len(bullets) <= MAX_BULLETS:
        raise ValueError(f"bad bullet count: {bullets!r}")
    out = []
    for b in bullets:
        t = int(b["t"])
        if t not in valid_ts:
            raise ValueError(f"ungrounded citation t={t}")
        txt = str(b["text"]).strip()
        if not 10 <= len(txt) <= 250:
            raise ValueError(f"bad bullet text: {txt!r}")
        out.append({"t": t, "time": mmss(t), "text": txt})
    return {"bullets": out, "source": "lyzr"}


def _local_note(moments: list) -> dict:
    """Deterministic fallback: top moments restated — grounded by construction."""
    bullets = []
    for m in moments[:MAX_BULLETS]:
        action = str(m.get("action", "")).replace("_", " ")
        desc = str(m.get("description", "")).strip().rstrip(".")
        bullets.append({"t": int(m["t"]), "time": mmss(m["t"]),
                        "text": f"{action}: {desc}." if desc else f"{action}."})
    return {"bullets": bullets, "source": "local"}
