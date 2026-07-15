"""Lyzr agent #1: natural-language query parser (stretch tier 1).

Calls the "FilmFinder Query Parser" agent in Lyzr Agent Studio and returns
the exact contract search.parse_query() produces, so the two are drop-in
interchangeable. Wired behind the USE_LYZR_PARSER flag in search.py.

Failure philosophy: this module raises on ANY problem — timeout, HTTP error,
malformed JSON, contract violation — and the caller falls back to the keyword
parser silently. It must never return a half-valid dict.
"""

import json
import os
import re
import uuid

import requests

LYZR_CHAT_URL = "https://agent-prod.studio.lyzr.ai/v3/inference/chat/"
DEFAULT_AGENT_ID = "6a57d686c5e6c811f5e7938b"
TIMEOUT_S = 6.0  # a stalled agent must not stall the demo

VALID_ACTIONS = {
    "corner", "free_kick", "penalty", "throw_in", "goal_kick", "shot",
    "save", "goal", "celebration", "tackle", "header", "dribble",
    "foul", "offside", "kickoff", "open_play", "break_or_crowd",
}
VIDEO_DURATION_S = 6275


def parse_query_lyzr(query: str) -> dict:
    """Raw query -> {action_filter, time_range, semantic_query, parser}."""
    api_key = os.environ["LYZR_API_KEY"]  # KeyError -> fallback
    agent_id = os.environ.get("LYZR_AGENT_ID", DEFAULT_AGENT_ID)
    resp = requests.post(
        LYZR_CHAT_URL,
        headers={"x-api-key": api_key, "Content-Type": "application/json"},
        json={
            "user_id": os.environ.get("LYZR_USER_ID", "filmfinder-app"),
            "agent_id": agent_id,
            # Fresh session per call: the parser is stateless, and shared
            # history would let one query's parse contaminate the next.
            "session_id": f"ffq-{uuid.uuid4().hex[:12]}",
            "message": query,
        },
        timeout=TIMEOUT_S,
    )
    resp.raise_for_status()
    text = resp.json()["response"].strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    data = json.loads(text)
    return _validate(data)


def _validate(data: dict) -> dict:
    """Enforce the contract; raise on anything the retrieval layer can't take."""
    if not isinstance(data, dict):
        raise ValueError("agent returned non-object")

    action = data.get("action_filter")
    if action is not None:
        action = str(action).strip().lower()
        if action not in VALID_ACTIONS:
            action = None  # unknown label: drop the filter, keep semantics

    tr = data.get("time_range")
    if tr is not None:
        if not isinstance(tr, (list, tuple)) or len(tr) != 2:
            raise ValueError(f"bad time_range: {tr!r}")
        gte, lte = tr
        gte = None if gte is None else max(0, int(gte))
        lte = None if lte is None else min(int(lte), VIDEO_DURATION_S)
        if gte is not None and lte is not None and lte <= gte:
            raise ValueError(f"empty time window: {tr!r}")
        tr = (gte, lte)

    sq = data.get("semantic_query", "")
    if not isinstance(sq, str):
        raise ValueError(f"bad semantic_query: {sq!r}")

    return {
        "action_filter": action,
        "time_range": tr,
        "semantic_query": " ".join(sq.lower().split()),
        "parser": "lyzr",
    }
