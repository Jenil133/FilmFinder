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


def parse_query(query: str, video_config: dict = VIDEO_CONFIG) -> dict:
    """Raw query -> {action_filter, time_range, semantic_query}."""
    q = query.strip()
    q_lower = " ".join(q.lower().split())
    semantic = q

    # --- time-range detection (phrase is stripped from the semantic query) ---
    time_range = None
    dur = video_config["duration_seconds"]

    m = re.search(r"\b(?:in\s+the\s+|during\s+the\s+)?first\s+half\b", q_lower)
    if m:
        time_range = (None, video_config["first_half_end_t"])
        semantic = (q_lower[: m.start()] + " " + q_lower[m.end():]).strip()
    if time_range is None:
        m = re.search(r"\b(?:in\s+the\s+|during\s+the\s+)?second\s+half\b", q_lower)
        if m:
            time_range = (video_config["second_half_start_t"], None)
            semantic = (q_lower[: m.start()] + " " + q_lower[m.end():]).strip()
    if time_range is None:
        m = re.search(r"\b(?:in\s+the\s+)?(?:last|final)\s+(\d+)\s+min(?:ute)?s?\b", q_lower)
        if m:
            time_range = (max(0, dur - 60 * int(m.group(1))), None)
            semantic = (q_lower[: m.start()] + " " + q_lower[m.end():]).strip()
    if time_range is None:
        m = re.search(r"\b(?:in\s+the\s+)?first\s+(\d+)\s+min(?:ute)?s?\b", q_lower)
        if m:
            time_range = (None, video_config["kickoff_t"] + 60 * int(m.group(1)))
            semantic = (q_lower[: m.start()] + " " + q_lower[m.end():]).strip()

    # --- action detection: longest matching synonym wins ---
    action = None
    sem_lower = " ".join(semantic.lower().split())
    for phrase in sorted(ACTION_SYNONYMS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(phrase)}\b", sem_lower):
            action = ACTION_SYNONYMS[phrase]
            break

    semantic = " ".join(semantic.split()) or q
    return {"action_filter": action, "time_range": time_range,
            "semantic_query": semantic}


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
            sys.exit("QDRANT_URL / QDRANT_API_KEY missing — fill .env (see .env.example)")
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
    parsed = parse_query(query)
    vec = list(get_embedder().query_embed(parsed["semantic_query"]))[0].tolist()
    client = get_client()

    qfilter = build_filter(parsed, include_action=True)
    if debug:
        print(f"  [debug] parsed: {parsed}")
        print(f"  [debug] qdrant filter: {qfilter}")
    hits = client.query_points(collection_name=collection, query=vec,
                               limit=top_k, query_filter=qfilter,
                               with_payload=True).points
    if not hits and parsed["action_filter"]:
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
