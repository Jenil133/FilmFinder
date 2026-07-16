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

# Match Pulse strip: categorical palette validated for CVD safety on the dark
# surface (#0f1116); identity is never color-alone — legend + tooltips.
PULSE_COLORS = {"goal": "#3987e5", "save": "#199e70", "corner": "#c98500",
                "shot": "#008300", "other": "#5f5e5a"}
PULSE_MARKER = "#e66767"  # search-result markers, distinct from all groups


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
@st.cache_data(ttl=86400, show_spinner=False)
def cached_search(query: str, collection: str):
    from search import find_moments
    return find_moments(query, collection=collection)


@st.cache_data(ttl=86400, show_spinner=False)
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


SURPRISE_PILL = "🎲 surprise me"


def on_pill():
    pick = st.session_state.get("chip_pills")
    if not pick:
        return
    if pick == SURPRISE_PILL:
        surprise_me()
    else:
        st.session_state.query_input = pick
    st.session_state.chip_pills = None  # re-arm so the same pill can fire twice


def jump_to(t: int):
    st.session_state.seek_t = int(t)
    if DEEPLINKS:
        try:
            st.query_params["t"] = str(int(t))
        except Exception:
            pass


def show_similar(m: dict, query: str):
    """Remember which moment to expand; the originating query is stored so a
    stale similar-row never renders under a different search's results."""
    st.session_state.similar_to = {"point_id": m["point_id"],
                                   "start_t": m["start_t"], "end_t": m["end_t"],
                                   "t": m["t"], "query": query}
    st.toast(f"Finding moments similar to {mmss(m['t'])}…", icon="✨")


@st.cache_data(ttl=86400, show_spinner=False)
def cached_similar(point_id: str, start_t: int, end_t: int, collection: str):
    from search import find_similar
    return find_similar(point_id, start_t, end_t, collection=collection)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_timeline(collection: str):
    from search import timeline_points
    return timeline_points(collection)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_stats(collection: str):
    from stats import match_events
    return match_events(collection)


def add_clip(m: dict, query: str):
    """Save a moment to the session clip board (deduped by timestamp)."""
    board = st.session_state.setdefault("clipboard", [])
    if not any(c["t"] == int(m["t"]) for c in board):
        board.append({"t": int(m["t"]), "action": m["action"],
                      "description": m["description"], "query": query})
        board.sort(key=lambda c: c["t"])
        st.toast(f"Saved {mmss(m['t'])} to the clip board", icon="📎")
    else:
        st.toast(f"{mmss(m['t'])} is already on the clip board", icon="📎")


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

st.set_page_config(page_title="FilmFinder", page_icon="🎬", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown("""<style>
[data-testid="stDecoration"] {display: none;}
[data-testid="stStatusWidget"] {visibility: hidden;}
header[data-testid="stHeader"] {background: transparent; height: 2rem;}
.block-container {padding-top: 1.2rem;}
</style>""", unsafe_allow_html=True)
load_settings()

# Deep links: ?q= pre-runs a search, ?t= pre-seeks the player. Inbound q goes
# through the same guardrails as typed queries (find_moments sanitizes).
DEEPLINKS = os.environ.get("ENABLE_DEEPLINKS", "1").lower() in ("1", "true", "yes")
_q0, _t0 = "", 0
if DEEPLINKS:
    try:
        from search import VIDEO_CONFIG
        _q0 = st.query_params.get("q", "")
        _t0 = min(max(int(st.query_params.get("t", "0")), 0),
                  VIDEO_CONFIG["duration_seconds"])
    except Exception:
        _q0, _t0 = "", 0

# Load alive: with no deep link, judges arrive mid-goal with a search already
# run — action on screen, markers on the strip, zero clicks required.
if not _q0:
    _q0 = "goal"
if not _t0:
    _t0 = 3734  # free-kick goal past the grey keeper (verified in QA.md)

st.session_state.setdefault("seek_t", _t0)
st.session_state.setdefault("query_input", _q0)

st.markdown("""
<div style="display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin-bottom:10px">
  <span style="font-size:2rem;font-weight:800">🎬 FilmFinder</span>
  <span style="color:#e66767;font-weight:600">Ctrl+F for game film</span>
</div>
<div style="display:flex;align-items:center;justify-content:center;gap:18px;
            background:#1a1d24;border:1px solid #2a2f3a;border-radius:10px;
            padding:10px 18px;margin-bottom:14px">
  <span style="text-transform:uppercase;letter-spacing:.12em;font-weight:700">Bournemouth</span>
  <span style="font-family:ui-monospace,monospace;font-size:1.6rem;font-weight:700;white-space:nowrap">4&#8239;–&#8239;3</span>
  <span style="text-transform:uppercase;letter-spacing:.12em;font-weight:700">Liverpool</span>
</div>
<div style="text-align:center;font-size:.7rem;text-transform:uppercase;
            letter-spacing:.14em;color:#8a8f9a;margin:-6px 0 12px">
  full match &middot; 3,138 frames indexed &middot; cc-by footage
</div>
""", unsafe_allow_html=True)

# ---- hero row: player left, search right ---------------------------------------
hero_l, hero_r = st.columns([3, 2], gap="large")

video_id = os.environ.get("VIDEO_ID", "")
with hero_l:
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

# ---- match overview ------------------------------------------------------------
if os.environ.get("SHOW_OVERVIEW", "1").lower() in ("1", "true", "yes"):
    try:
        from stats import HEADLINE_STATS
        counts = cached_stats(COLLECTION)
        with st.expander("📊 Match overview — every stat is clickable"):
            stat_cols = st.columns(len(HEADLINE_STATS))
            for col, (a, label, q) in zip(stat_cols, HEADLINE_STATS):
                s = counts[a]
                col.button(f"**{s['total']}**  \n{label}", key=f"stat_{a}",
                           on_click=set_query, args=(q,),
                           help=f"1st half {s['h1']} · 2nd half {s['h2']}",
                           use_container_width=True)
            st.caption("caption-derived event moments (replays can double-count) "
                       "— not official match stats")
    except Exception:
        pass

# ---- search bar + chips (rendered into the hero's right column) ---------------
with hero_r:
    st.markdown("##### Search the match")
    query = st.text_input(
        "Search the match",
        key="query_input",
        label_visibility="collapsed",
        placeholder='Try "corner kick" or "players arguing with the referee"...',
    )
    st.pills("Suggestions", CHIPS + [SURPRISE_PILL], key="chip_pills",
             on_change=on_pill, label_visibility="collapsed")

# Warm the engine at startup (not on first search): on Streamlit Cloud the
# fastembed model download costs 10-40s — pay it while the page is being read.
_, mmss = engine()  # searches go through cached_search; engine() pre-warms models

# ---- clip board (sidebar) ------------------------------------------------------
if os.environ.get("ENABLE_CLIPBOARD", "1").lower() in ("1", "true", "yes"):
    clips = st.session_state.get("clipboard", [])
    with st.sidebar:
        st.toggle("🔬 X-ray mode", key="xray",
                  help="Expose the pipeline: parsed query contract, the exact "
                       "Qdrant filter, per-stage latency, similarity scores.")
        st.divider()
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
                   + (f" · filters — {' · '.join(filters)}" if filters else "")
                   + (" · 🔗 page URL is shareable" if DEEPLINKS else ""))
        if DEEPLINKS:
            try:
                if st.query_params.get("q") != query:
                    st.query_params["q"] = query
            except Exception:
                pass
        if parsed.get("action_filter_dropped"):
            st.caption(f"⚠️ No moments labeled *{parsed['action_filter']}* — "
                       "showing the closest semantic matches instead.")
        if parsed.get("sanitized"):
            st.caption("🛡️ Parts of that query looked like instructions rather "
                       "than soccer — searched a cleaned version.")

        pulse_moments = moments

        if st.session_state.get("xray"):
            with st.expander("🔬 X-ray — what just happened", expanded=True):
                tm = parsed.get("timings", {})
                xcols = st.columns(3)
                xcols[0].metric("parse", f"{tm.get('parse_ms', 0):.0f} ms",
                                help=f"parser: {parsed.get('parser', '?')}")
                xcols[1].metric("embed", f"{tm.get('embed_ms', 0):.0f} ms",
                                help="bge-small-en-v1.5, 384-dim, local")
                xcols[2].metric("Qdrant", f"{tm.get('qdrant_ms', 0):.0f} ms",
                                help="hybrid query, cloud round-trip")
                st.markdown("**Parsed contract**")
                st.json({k: parsed.get(k) for k in
                         ("parser", "action_filter", "time_range",
                          "semantic_query", "action_filter_dropped", "sanitized")
                         if parsed.get(k) is not None})
                st.markdown("**Qdrant filter (as executed)**")
                st.json(parsed.get("qdrant_filter")
                        or {"filter": "none — pure semantic search"})

        # Scout Note panel: reserve the slot now, fill it after the cards
        # render so the agent's latency never delays the results.
        note_slot = st.container()

        show_sim = os.environ.get("SHOW_SIMILAR", "1").lower() in ("1", "true", "yes")
        for row_start in range(0, len(moments), 3):
            cols = st.columns(3)
            for col, m in zip(cols, moments[row_start: row_start + 3]):
                with col, st.container(border=True):
                    thumb = THUMBS_DIR / m["frame"]
                    if thumb.exists():
                        st.image(str(thumb), use_container_width=True)
                    dot = PULSE_COLORS.get(m["action"], PULSE_COLORS["other"])
                    st.markdown(
                        f"**{mmss(m['t'])}** &nbsp;"
                        f"<span style='color:{dot}'>●</span> "
                        f"<small>{m['action'].replace('_', ' ')}</small>  \n"
                        f"{m['description']}",
                        unsafe_allow_html=True)
                    if st.session_state.get("xray"):
                        st.progress(max(0.0, min(float(m["score"]), 1.0)),
                                    text=f"similarity {m['score']:.3f}")
                    st.button(f"▶ Jump to {mmss(m['t'])}", key=f"jump_{m['t']}",
                              on_click=jump_to, args=(m["t"],),
                              use_container_width=True)
                    bcols = st.columns(2)
                    if show_sim and m.get("point_id"):
                        bcols[0].button("✨ Similar", key=f"sim_{m['t']}",
                                        on_click=show_similar, args=(m, query),
                                        use_container_width=True)
                    bcols[1].button("➕ Save", key=f"save_{m['t']}",
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
                    with col, st.container(border=True):
                        thumb = THUMBS_DIR / m["frame"]
                        if thumb.exists():
                            st.image(str(thumb), use_container_width=True)
                        dot = PULSE_COLORS.get(m["action"], PULSE_COLORS["other"])
                        st.markdown(
                            f"**{mmss(m['t'])}** &nbsp;"
                            f"<span style='color:{dot}'>●</span> "
                            f"<small>{m['action'].replace('_', ' ')}</small>  \n"
                            f"{m['description']}",
                            unsafe_allow_html=True)
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
