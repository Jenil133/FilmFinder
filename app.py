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
