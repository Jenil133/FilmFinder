"""Match Overview: per-half event counts computed from the caption index.

Consecutive frames sharing an action label within a small gap are one EVENT
(a corner takes ~3 captions; counting frames would triple every stat). The
headline stats are curated to action labels the captioner is reliable on —
'goal' is deliberately excluded from headlines because replays inflate it
(measured on the full corpus); the search path still handles goal queries.
"""

from search import VIDEO_CONFIG, get_client

# 20s: one event per distinct sequence (prep -> delivery reads as one corner;
# measured against gap=4/8/12 — 20s lands nearest plausible real-match counts).
# Replays airing later can still double-count: the UI labels these as
# caption-derived moments, never official stats.
MERGE_GAP_S = 20

# (action label, display name, query the stat fires when clicked)
HEADLINE_STATS = [
    ("corner", "corners", "corner kick"),
    ("shot", "shots", "shot on goal"),
    ("save", "saves", "goalkeeper save"),
    ("throw_in", "throw-ins", "throw-in"),
    ("free_kick", "free kicks", "free kick"),
    ("foul", "fouls", "foul"),
]


def match_events(collection: str):
    """-> {action: {"total": n, "h1": n, "h2": n}} for the headline actions."""
    client = get_client()
    rows, offset = [], None
    while True:
        points, offset = client.scroll(collection_name=collection, limit=1000,
                                       offset=offset,
                                       with_payload=["t", "action"],
                                       with_vectors=False)
        rows.extend((p.payload["t"], p.payload["action"]) for p in points)
        if offset is None:
            break
    rows.sort()

    wanted = {a for a, _, _ in HEADLINE_STATS}
    events = []  # (action, start_t)
    last = {}    # action -> last t seen, for gap merging
    for t, action in rows:
        if action not in wanted:
            continue
        if action in last and t - last[action] <= MERGE_GAP_S:
            last[action] = t  # same event continues
            continue
        last[action] = t
        events.append((action, t))

    fh_end = VIDEO_CONFIG["first_half_end_t"]
    counts = {a: {"total": 0, "h1": 0, "h2": 0} for a in wanted}
    for action, t in events:
        c = counts[action]
        c["total"] += 1
        c["h1" if t <= fh_end else "h2"] += 1
    return counts
