"""FilmFinder — search a soccer match in plain English, click a result, and
the video jumps to that moment.

App v1 (Phase 2): runs against the dev index. Thursday's swap to the full
match is the two constants below (COLLECTION, THUMBS_DIR) — nothing else.
"""

import os
from pathlib import Path

import streamlit as st

# ---- Full match (swapped Thursday from the filmfinder_dev slice) -----------
COLLECTION = "filmfinder_match01"
THUMBS_DIR = Path(__file__).parent / "thumbs/match01"  # cwd-independent
# -----------------------------------------------------------------------------

CHIPS = ["corner kick", "goalkeeper save", "shot on goal",
         "throw-in", "celebration", "tackle in the box"]
# Longer tail than the chips — the surprise button's job is showing range.
SURPRISE_QUERIES = CHIPS + [
    "players arguing with the referee",
    "when did the keeper mess up",
    "diving save",
    "free kick near the box",
    "header",
    "goals in the second half",
    "shots in the last 10 minutes",
    "injury stoppage",
    "fans celebrating",
]
SEEK_BUILDUP_S = 3  # land a beat before the moment

# Match Pulse strip: categorical palette validated for CVD safety (worst
# adjacent deutan ΔE 13.3); identity is never color-alone — legend + tooltips.
PULSE_COLORS = {"goal": "#2a78d6", "save": "#1baf7a", "corner": "#eda100",
                "shot": "#008300", "other": "#b4b2a9"}
PULSE_MARKER = "#e34948"  # search-result markers, distinct from all groups


def load_settings():
    """Streamlit secrets (deployed) win; fall back to .env (local)."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    for name in ("QDRANT_URL", "QDRANT_API_KEY", "VIDEO_ID",
                 "LYZR_API_KEY", "USE_LYZR_PARSER", "LYZR_AGENT_ID",
                 "USE_LYZR_SCOUT", "LYZR_SCOUT_AGENT_ID"):
        try:
            if name in st.secrets:
                os.environ[name] = str(st.secrets[name])
        except Exception:
            pass  # no secrets.toml locally — .env already loaded


@st.cache_resource(show_spinner="Warming up the search engine...")
def engine():
    """Embedding model + Qdrant client, created once per server process."""
    from search import get_client, get_embedder
    get_embedder()
    get_client()
    try:  # pre-pay first-inference + TLS handshake so search #1 is instant
        # assigned, not bare: Streamlit magic auto-renders bare expressions
        _warm = list(get_embedder().query_embed("warmup"))[0]
        _info = get_client().get_collection(COLLECTION)
    except Exception:
        pass  # warmup is best-effort; real calls surface real errors
    from search import find_moments, mmss
    return find_moments, mmss


# Streamlit reruns this whole script on EVERY widget interaction (jump
# clicks, chips, toggles). Without these caches each rerun re-bought the same
# search — including both Lyzr agent calls — from a ~20-credit monthly pool.
# Only successful results are cached; errors stay retryable.
@st.cache_data(ttl=600, show_spinner=False)
def cached_search(query: str, collection: str):
    from search import find_moments
    return find_moments(query, collection=collection)


@st.cache_data(ttl=600, show_spinner=False)
def cached_note(query: str, moments: list):
    from scout_note import scout_note
    return scout_note(query, moments)


def run_search(query: str):
    try:
        parsed, moments = cached_search(query, COLLECTION)
        return parsed, moments, None
    except Exception as e:
        return None, [], f"Search hiccup ({type(e).__name__}) — try again in a moment."


def set_query(q: str):
    st.session_state.query_input = q


def surprise_me():
    import random
    pool = [q for q in SURPRISE_QUERIES
            if q != st.session_state.get("query_input")]
    st.session_state.query_input = random.choice(pool)


def jump_to(t: int):
    st.session_state.seek_t = int(t)


def show_similar(m: dict, query: str):
    """Remember which moment to expand; the originating query is stored so a
    stale similar-row never renders under a different search's results."""
    st.session_state.similar_to = {"point_id": m["point_id"],
                                   "start_t": m["start_t"], "end_t": m["end_t"],
                                   "t": m["t"], "query": query}


@st.cache_data(ttl=600, show_spinner=False)
def cached_similar(point_id: str, start_t: int, end_t: int, collection: str):
    from search import find_similar
    return find_similar(point_id, start_t, end_t, collection=collection)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_timeline(collection: str):
    from search import timeline_points
    return timeline_points(collection)


def add_clip(m: dict, query: str):
    """Save a moment to the session clip board (deduped by timestamp)."""
    board = st.session_state.setdefault("clipboard", [])
    if not any(c["t"] == int(m["t"]) for c in board):
        board.append({"t": int(m["t"]), "action": m["action"],
                      "description": m["description"], "query": query})
        board.sort(key=lambda c: c["t"])


def remove_clip(t: int):
    st.session_state.clipboard = [c for c in st.session_state.get("clipboard", [])
                                  if c["t"] != t]


def clipboard_markdown(clips: list, video_id: str) -> str:
    """Session plan a coach can paste into the team chat: every line is a
    working YouTube deep link straight to the moment."""
    lines = ["# FilmFinder session plan", ""]
    for c in clips:
        ts = mmss(c["t"])
        link = (f"[{ts}](https://youtu.be/{video_id}?t={c['t']})"
                if video_id else f"**{ts}**")
        action = c["action"].replace("_", " ")
        lines.append(f"- {link} — {action}: {c['description']} "
                     f"_(found via “{c['query']}”)_")
    return "\n".join(lines) + "\n"


def pulse_seek():
    """Chart-click callback. Runs BEFORE the script rerun, so the player
    iframe (rendered above the chart) picks up the new seek this same run."""
    try:
        pts = st.session_state["pulse"]["selection"]["seek"]
        if pts:
            jump_to(int(pts[0]["t"]))
    except Exception:
        pass  # deselect events carry no points


def render_pulse(slot, moments: list):
    """Match Pulse: every indexed frame as an action-colored tick across the
    full video, with the current search's moments as clickable markers."""
    import altair as alt
    import pandas as pd
    from search import VIDEO_CONFIG

    rows = cached_timeline(COLLECTION)
    if not rows:
        return
    df = pd.DataFrame(rows, columns=["t", "action"])
    df["group"] = df["action"].where(df["action"].isin(PULSE_COLORS), "other")
    df["min"] = df["t"] / 60.0
    df["time"] = df["t"].apply(mmss)
    domain = ["goal", "save", "corner", "shot", "other"]
    dur_min = VIDEO_CONFIG["duration_seconds"] / 60.0

    base = alt.Chart(df).mark_tick(thickness=2, size=16).encode(
        x=alt.X("min:Q", title=None,
                scale=alt.Scale(domain=[0, dur_min], nice=False),
                axis=alt.Axis(grid=False, labelExpr='datum.value + "′"')),
        color=alt.Color("group:N", title=None,
                        scale=alt.Scale(domain=domain,
                                        range=[PULSE_COLORS[g] for g in domain]),
                        legend=alt.Legend(orient="top", direction="horizontal")),
        opacity=alt.condition(alt.datum.group == "other",
                              alt.value(0.18), alt.value(0.85)),
        tooltip=[alt.Tooltip("time:N", title="video"),
                 alt.Tooltip("action:N")],
    ).properties(height=72)

    chart = base
    if moments:
        mdf = pd.DataFrame([{"min": m["t"] / 60.0, "t": int(m["t"]),
                             "time": mmss(m["t"]), "action": m["action"]}
                            for m in moments])
        sel = alt.selection_point(name="seek", fields=["t"], on="click")
        marks = alt.Chart(mdf).mark_point(
            shape="triangle-down", size=200, filled=True,
            color=PULSE_MARKER, opacity=1, yOffset=-16,
        ).encode(
            x="min:Q",
            tooltip=[alt.Tooltip("time:N", title="jump to"),
                     alt.Tooltip("action:N")],
        ).add_params(sel)
        chart = base + marks

    with slot:
        if moments:
            # on_select is only legal when the chart carries a selection param
            st.altair_chart(chart, use_container_width=True, key="pulse",
                            on_select=pulse_seek)
            st.caption("🔻 your search, across the whole match — click a marker to jump there")
        else:
            st.altair_chart(chart, use_container_width=True)


# --------------------------------------------------------------------------- #

st.set_page_config(page_title="FilmFinder", page_icon="🎬", layout="centered")
load_settings()

st.session_state.setdefault("seek_t", 0)
st.session_state.setdefault("query_input", "")

st.title("🎬 FilmFinder")
st.caption("Ctrl+F for game film — type what happened, jump straight to it. "
           "Playback is muted on arrival (browser autoplay policy); unmute in the player.")

# ---- player ------------------------------------------------------------------
video_id = os.environ.get("VIDEO_ID", "")
if video_id:
    start = max(st.session_state.seek_t - SEEK_BUILDUP_S, 0)
    st.iframe(
        f"https://www.youtube.com/embed/{video_id}?start={start}&autoplay=1&mute=1",
        height=400,
    )
else:
    st.warning("No VIDEO_ID configured — set it in .env locally or in the "
               "Streamlit secrets dashboard.")

# Match Pulse slot: reserved here (under the player), filled at the end of
# the script once the search results exist. SHOW_TIMELINE is the kill switch.
SHOW_PULSE = os.environ.get("SHOW_TIMELINE", "1").lower() in ("1", "true", "yes")
pulse_slot = st.container() if SHOW_PULSE else None
pulse_moments = []

# ---- search bar + chips -------------------------------------------------------
query = st.text_input(
    "Search the match",
    key="query_input",
    placeholder='Try "corner kick" or "players arguing with the referee"...',
)
chip_cols = st.columns(3)
for i, chip in enumerate(CHIPS):
    chip_cols[i % 3].button(chip, key=f"chip_{i}", on_click=set_query,
                            args=(chip,), use_container_width=True)
st.button("🎲 Surprise me", key="surprise", on_click=surprise_me,
          use_container_width=True)

# Warm the engine at startup (not on first search): on Streamlit Cloud the
# fastembed model download costs 10-40s — pay it while the page is being read.
_, mmss = engine()  # searches go through cached_search; engine() pre-warms models

# ---- clip board (sidebar) ------------------------------------------------------
if os.environ.get("ENABLE_CLIPBOARD", "1").lower() in ("1", "true", "yes"):
    clips = st.session_state.get("clipboard", [])
    with st.sidebar:
        st.subheader(f"📎 Clip board ({len(clips)})")
        if not clips:
            st.caption("Save moments from the results, then export a session "
                       "plan with timestamped video links for your team.")
        for c in clips:
            row = st.columns([5, 1])
            row[0].markdown(f"**{mmss(c['t'])}** · {c['action'].replace('_', ' ')}")
            row[1].button("✕", key=f"rm_{c['t']}", on_click=remove_clip,
                          args=(c["t"],))
        if clips:
            st.download_button("⬇️ Export session plan (.md)",
                               clipboard_markdown(clips, video_id),
                               file_name="session_plan.md",
                               mime="text/markdown", use_container_width=True)

# ---- results ------------------------------------------------------------------
if not query:
    st.info("Search anything you'd scrub the timeline for — or tap a suggestion above.")
else:
    with st.spinner(f'Searching for "{query}"...'):
        parsed, moments, error = run_search(query)

    if error:
        st.error(error)
    elif not moments:
        st.warning(f'No moments found for "{query}" — the footage may not contain it. '
                   "Try one of the suggestions above, or looser phrasing.")
    else:
        filters = []
        if parsed["action_filter"]:
            filters.append(f"action: {parsed['action_filter']}")
        if parsed["time_range"]:
            gte, lte = parsed["time_range"]
            filters.append(f"time: {mmss(gte) if gte else 'start'} → "
                           f"{mmss(lte) if lte else 'end'}")
        st.caption(f"{len(moments)} moment{'s' if len(moments) != 1 else ''}"
                   + (f" · filters — {' · '.join(filters)}" if filters else ""))
        if parsed.get("action_filter_dropped"):
            st.caption(f"⚠️ No moments labeled *{parsed['action_filter']}* — "
                       "showing the closest semantic matches instead.")
        if parsed.get("sanitized"):
            st.caption("🛡️ Parts of that query looked like instructions rather "
                       "than soccer — searched a cleaned version.")

        pulse_moments = moments

        # Scout Note panel: reserve the slot now, fill it after the cards
        # render so the agent's latency never delays the results.
        note_slot = st.container()

        show_sim = os.environ.get("SHOW_SIMILAR", "1").lower() in ("1", "true", "yes")
        for row_start in range(0, len(moments), 3):
            cols = st.columns(3)
            for col, m in zip(cols, moments[row_start: row_start + 3]):
                with col:
                    thumb = THUMBS_DIR / m["frame"]
                    if thumb.exists():
                        st.image(str(thumb), use_container_width=True)
                    st.markdown(f"**{mmss(m['t'])}**  \n{m['description']}")
                    st.button(f"▶ Jump to {mmss(m['t'])}", key=f"jump_{m['t']}",
                              on_click=jump_to, args=(m["t"],),
                              use_container_width=True)
                    if show_sim and m.get("point_id"):
                        st.button("✨ More like this", key=f"sim_{m['t']}",
                                  on_click=show_similar, args=(m, query),
                                  use_container_width=True)
                    st.button("➕ Save clip", key=f"save_{m['t']}",
                              on_click=add_clip, args=(m, query),
                              use_container_width=True)

        # "More like this" row — Qdrant recommend-by-point on the clicked
        # moment's stored vector. Only rendered for the query it came from.
        sim = st.session_state.get("similar_to")
        if show_sim and sim and sim["query"] == query:
            st.divider()
            st.subheader(f"Moments similar to {mmss(sim['t'])}")
            try:
                similar = cached_similar(sim["point_id"], sim["start_t"],
                                         sim["end_t"], COLLECTION)
            except Exception:
                similar = None
            if similar is None:
                st.caption("Similarity search hiccup — try again in a moment.")
            elif not similar:
                st.caption("Nothing else in the match looks like this moment.")
            else:
                sim_cols = st.columns(len(similar))
                for col, m in zip(sim_cols, similar):
                    with col:
                        thumb = THUMBS_DIR / m["frame"]
                        if thumb.exists():
                            st.image(str(thumb), use_container_width=True)
                        st.markdown(f"**{mmss(m['t'])}**  \n{m['description']}")
                        st.button(f"▶ Jump to {mmss(m['t'])}",
                                  key=f"simjump_{m['t']}", on_click=jump_to,
                                  args=(m["t"],), use_container_width=True)

        note = cached_note(query, moments)
        if note:
            with note_slot:
                tag = " · by Lyzr agent" if note["source"] == "lyzr" else ""
                with st.expander(f"📋 Scout Note{tag}", expanded=True):
                    for b in note["bullets"]:
                        st.markdown(f"- **{b['time']}** — {b['text']}")

# Fill the Match Pulse slot last: a chart failure must never take down the
# search experience — the strip just doesn't appear.
if SHOW_PULSE:
    try:
        render_pulse(pulse_slot, pulse_moments)
    except Exception:
        pass
