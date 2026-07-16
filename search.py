"""FilmFinder runtime engine: query understanding -> hybrid retrieval -> moment clustering.

The contract every query-understanding path must satisfy (the Lyzr agent in
Phase 3 sits in front of this behind a flag and returns the same shape):

    {"action_filter": str|None, "time_range": (gte|None, lte|None)|None,
     "semantic_query": str}

Usage (sanity checks / QA):
    python search.py "corner kick"
    python search.py "the red team's corners in the second half" --debug
"""

import argparse
import functools
import json
import os
import re
import sys

from dotenv import load_dotenv

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_COLLECTION = "filmfinder_dev"

# Per-video timeline facts (video time != match clock: intros, halftime break).
# Measured from the scoreboard clock in probe frames — see KILLTEST.md context.
VIDEO_CONFIG = {
    "video_id": "k5mB9aOIgrY",
    "duration_seconds": 6275,
    "kickoff_t": 113,            # match clock 0:00 is at video t=113
    "first_half_end_t": 2900,    # ~45:00 + stoppage
    "second_half_start_t": 3085, # match clock 45:00 restart at video t=3085
}

ACTIONS = [
    "corner", "free_kick", "penalty", "throw_in", "goal_kick", "shot",
    "save", "goal", "celebration", "tackle", "header", "dribble",
    "foul", "offside", "kickoff", "open_play", "break_or_crowd",
]

# Chip vocabulary + obvious synonyms -> taxonomy action. Longest phrase wins,
# so "goal kick" resolves before "goal" and "shot on goal" before "goal".
ACTION_SYNONYMS = {
    "corner kick": "corner", "corner kicks": "corner", "corners": "corner",
    "corner": "corner",
    "goalkeeper save": "save", "keeper save": "save", "goalie save": "save",
    "diving save": "save", "saves": "save", "save": "save",
    "shot on goal": "shot", "shot on target": "shot", "shots": "shot",
    "shoots": "shot", "shot": "shot", "strike on goal": "shot",
    "throw-in": "throw_in", "throw in": "throw_in", "throw-ins": "throw_in",
    "throw ins": "throw_in", "throwin": "throw_in",
    "goal celebration": "celebration", "celebrations": "celebration",
    "celebrating": "celebration", "celebrate": "celebration",
    "celebration": "celebration",
    "goal kick": "goal_kick", "goal kicks": "goal_kick",
    "free kick": "free_kick", "free-kick": "free_kick", "free kicks": "free_kick",
    "penalty kick": "penalty", "spot kick": "penalty", "penalty": "penalty",
    "tackle in the box": "tackle", "sliding tackle": "tackle",
    "tackles": "tackle", "tackle": "tackle",
    "headers": "header", "header": "header",
    "dribbling": "dribble", "dribbles": "dribble", "dribble": "dribble",
    "fouls": "foul", "foul": "foul",
    "offside": "offside", "offsides": "offside",
    "kickoff": "kickoff", "kick off": "kickoff", "kick-off": "kickoff",
    "goals": "goal", "goal": "goal", "scores a goal": "goal",
}


# Bare "corner"/"goal" are hijack-prone: "shot into the bottom corner" is a
# shot, "goal line clearance" is a goal PREVENTED. Guards below skip the bare
# synonym when the positional/compound phrase is present.
_POSITIONAL_CORNER = re.compile(r"\b(?:bottom|top|far|near|upper|lower|back)\s+corner\b")
_GOAL_LINE = re.compile(r"\bgoal[\s-]+line\b")


def parse_query(query: str, video_config: dict = VIDEO_CONFIG) -> dict:
    """Raw query -> {action_filter, time_range, semantic_query}."""
    q = query.strip()
    semantic = " ".join(q.lower().split())
    dur = video_config["duration_seconds"]
    kickoff = video_config["kickoff_t"]
    fh_end = video_config["first_half_end_t"]
    sh_start = video_config["second_half_start_t"]

    def strip_match(text, m):
        return (text[: m.start()] + " " + text[m.end():]).strip()

    # --- time-range detection ------------------------------------------------
    # Halves first, then relative windows ANCHORED to the detected half, so
    # "last 10 minutes of the first half" means (fh_end - 600, fh_end), not
    # the whole first half. Every recognized phrase is stripped from the
    # semantic text.
    stripped_time = False
    half = None
    m = re.search(r"\b(?:in\s+the\s+|during\s+the\s+|of\s+the\s+)?first[\s-]+half\b", semantic)
    if m:
        half, semantic, stripped_time = "first", strip_match(semantic, m), True
    else:
        m = re.search(r"\b(?:in\s+the\s+|during\s+the\s+|of\s+the\s+)?second[\s-]+half\b", semantic)
        if m:
            half, semantic, stripped_time = "second", strip_match(semantic, m), True

    if half == "first":
        bounds = [kickoff, fh_end]  # gte excludes pre-kickoff intro footage
    elif half == "second":
        bounds = [sh_start, None]
    else:
        bounds = None

    m = re.search(r"\b(?:in\s+the\s+)?(?:last|final)\s+(\d+)\s+min(?:ute)?s?\b", semantic)
    if m:
        n = int(m.group(1))
        if half == "first":
            bounds = [max(kickoff, fh_end - 60 * n), fh_end]
        else:  # second half or whole video: both end at the video's end
            bounds = [max(0, dur - 60 * n), None]
        semantic, stripped_time = strip_match(semantic, m), True
    else:
        m = re.search(r"\b(?:in\s+the\s+)?first\s+(\d+)\s+min(?:ute)?s?\b", semantic)
        if m:
            n = int(m.group(1))
            if half == "second":
                bounds = [sh_start, sh_start + 60 * n]
            else:
                lte = kickoff + 60 * n
                if lte > fh_end:  # window spills past halftime: skip the break
                    lte = sh_start + 60 * (n - 45)
                bounds = [kickoff, lte]
            semantic, stripped_time = strip_match(semantic, m), True

    time_range = tuple(bounds) if bounds else None

    # --- action detection: longest matching synonym wins ---------------------
    action = None
    sem_lower = " ".join(semantic.split())
    for phrase in sorted(ACTION_SYNONYMS, key=len, reverse=True):
        if not re.search(rf"\b{re.escape(phrase)}\b", sem_lower):
            continue
        target = ACTION_SYNONYMS[phrase]
        if target == "corner" and phrase in ("corner", "corners") \
                and _POSITIONAL_CORNER.search(sem_lower):
            continue  # "bottom corner" is a location, not a corner kick
        if target == "goal" and _GOAL_LINE.search(sem_lower):
            continue  # "goal line clearance" is not a goal
        action = target
        break

    # Pure time-phrase queries ("second half") must NOT reinstate the stripped
    # phrase as the semantic text — rank by a neutral query instead (search()
    # handles the empty string). Only fall back to the original when nothing
    # was recognized at all.
    cleaned = " ".join(semantic.split())
    if cleaned:
        semantic_query = cleaned
    elif stripped_time or action:
        semantic_query = ""
    else:
        semantic_query = " ".join(q.lower().split())

    return {"action_filter": action, "time_range": time_range,
            "semantic_query": semantic_query, "parser": "keyword"}


@functools.lru_cache(maxsize=128)
def _lyzr_parse_cached(query: str) -> dict:
    """Successful Lyzr parses are cached per query: Streamlit reruns the whole
    script on every widget click, and without this each click re-bought the
    same parse with a fresh Lyzr credit. lru_cache skips failures, so errors
    are retried, not remembered."""
    from lyzr_parser import parse_query_lyzr
    return parse_query_lyzr(query)


def parse_query_flagged(query: str) -> dict:
    """Lyzr agent parser when USE_LYZR_PARSER is on; keyword parser otherwise.

    Any Lyzr failure (missing key, timeout, malformed output) falls back
    silently — the flag can never make the product worse than the baseline.
    The shared circuit breaker (lyzr_guard) turns a dead Lyzr API from a
    6s-per-search timeout tax into one skipped call.
    """
    load_dotenv()  # CLI path reaches here before get_client()'s load
    if os.environ.get("USE_LYZR_PARSER", "").lower() in ("1", "true", "yes"):
        import lyzr_guard
        if lyzr_guard.allowed():
            try:
                parsed = _lyzr_parse_cached(query)
                lyzr_guard.record(True)
                return dict(parsed)  # shallow copy: callers add keys
            except Exception:
                lyzr_guard.record(False)
    return parse_query(query)


# --------------------------------------------------------------------------- #
# Retrieval
# --------------------------------------------------------------------------- #

_embedder = None
_client = None


def get_embedder():
    global _embedder
    if _embedder is None:
        from fastembed import TextEmbedding
        _embedder = TextEmbedding(model_name=EMBED_MODEL)
    return _embedder


def get_client():
    global _client
    if _client is None:
        from qdrant_client import QdrantClient
        load_dotenv()
        url, key = os.environ.get("QDRANT_URL"), os.environ.get("QDRANT_API_KEY")
        if not url or not key:
            # RuntimeError (not sys.exit): Streamlit renders exceptions but a
            # SystemExit silently kills the script thread and hangs the page.
            raise RuntimeError("QDRANT_URL / QDRANT_API_KEY missing — fill .env "
                               "or the Streamlit secrets dashboard")
        _client = QdrantClient(url=url, api_key=key, timeout=30)
    return _client


def build_filter(parsed: dict, include_action: bool = True):
    from qdrant_client.models import FieldCondition, Filter, MatchValue, Range
    conditions = []
    if include_action and parsed["action_filter"]:
        conditions.append(FieldCondition(key="action",
                                         match=MatchValue(value=parsed["action_filter"])))
    if parsed["time_range"]:
        gte, lte = parsed["time_range"]
        conditions.append(FieldCondition(key="t", range=Range(gte=gte, lte=lte)))
    return Filter(must=conditions) if conditions else None


def search(query: str, collection: str = DEFAULT_COLLECTION, top_k: int = 25,
           debug: bool = False):
    """Full runtime path: parse -> hybrid retrieval. Returns (parsed, hits).

    Semantic vector search always runs; action/time become payload filters when
    detected. If a hard action filter yields nothing (VLM labeling gaps), we
    retry on semantics alone so the long-tail path still carries the query.
    """
    from guardrails import sanitize_query
    query, flagged = sanitize_query(query)
    parsed = parse_query_flagged(query)
    if flagged:
        parsed = {**parsed, "sanitized": True}
    # Empty semantic text (pure time/action-phrase query) ranks by a neutral
    # probe so ordering isn't driven by similarity to e.g. "second half".
    embed_text = parsed["semantic_query"] or "soccer match action"
    vec = list(get_embedder().query_embed(embed_text))[0].tolist()
    client = get_client()

    qfilter = build_filter(parsed, include_action=True)
    if debug:
        print(f"  [debug] parsed: {parsed}")
        print(f"  [debug] qdrant filter: {qfilter}")
    hits = client.query_points(collection_name=collection, query=vec,
                               limit=top_k, query_filter=qfilter,
                               with_payload=True).points
    if not hits and parsed["action_filter"]:
        # No frames carry this action label (VLM gap, or it never happened).
        # Degrade to semantics-only — but SAY so, so the UI can disclose it.
        parsed = {**parsed, "action_filter_dropped": True}
        qfilter = build_filter(parsed, include_action=False)
        if debug:
            print(f"  [debug] action filter empty -> semantic fallback, filter: {qfilter}")
        hits = client.query_points(collection_name=collection, query=vec,
                                   limit=top_k, query_filter=qfilter,
                                   with_payload=True).points
    return parsed, hits


# --------------------------------------------------------------------------- #
# Moment clustering
# --------------------------------------------------------------------------- #

def cluster_moments(hits, gap_seconds: int = 10, max_moments: int = 6):
    """Merge frame hits within gap_seconds of each other into one moment.

    Representative frame = highest-score hit in the cluster. Returns up to
    max_moments moments sorted by score (desc).
    """
    if not hits:
        return []
    by_time = sorted(hits, key=lambda h: h.payload["t"])
    clusters = [[by_time[0]]]
    for h in by_time[1:]:
        if h.payload["t"] - clusters[-1][-1].payload["t"] <= gap_seconds:
            clusters[-1].append(h)
        else:
            clusters.append([h])

    moments = []
    for cluster in clusters:
        rep = max(cluster, key=lambda h: h.score)
        moments.append({
            "t": rep.payload["t"],
            "start_t": cluster[0].payload["t"],
            "end_t": cluster[-1].payload["t"],
            "score": rep.score,
            "frame": rep.payload["frame"],
            "video": rep.payload.get("video", ""),
            "action": rep.payload["action"],
            "description": rep.payload["description"],
            "n_frames": len(cluster),
        })
    moments.sort(key=lambda m: m["score"], reverse=True)
    return moments[:max_moments]


def find_moments(query: str, collection: str = DEFAULT_COLLECTION,
                 top_k: int = 25, max_moments: int = 6, debug: bool = False):
    """The one call the UI makes: query in, clustered moments out."""
    parsed, hits = search(query, collection=collection, top_k=top_k, debug=debug)
    return parsed, cluster_moments(hits, max_moments=max_moments)


def mmss(t: float) -> str:
    t = int(t)
    if t >= 3600:
        return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"
    return f"{t // 60}:{t % 60:02d}"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("query")
    ap.add_argument("--collection", default=DEFAULT_COLLECTION)
    ap.add_argument("--top-k", type=int, default=25)
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    parsed, moments = find_moments(args.query, collection=args.collection,
                                   top_k=args.top_k, debug=args.debug)
    print(f"query: {args.query!r}")
    print(f"parsed: {json.dumps(parsed)}")
    if not moments:
        print("no moments found")
        return
    for i, m in enumerate(moments, 1):
        span = f" (spans {m['start_t']}-{m['end_t']}s, {m['n_frames']} frames)" \
            if m["n_frames"] > 1 else ""
        print(f"{i}. t={mmss(m['t'])} ({m['t']}s) · score={m['score']:.3f} · "
              f"{m['action']}{span}")
        print(f"   {m['description']} [{m['frame']}]")


if __name__ == "__main__":
    main()
