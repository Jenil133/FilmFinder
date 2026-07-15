"""FilmFinder — search a soccer match in plain English, click a result, and
the video jumps to that moment.

App v1 (Phase 2): runs against the dev index. Thursday's swap to the full
match is the two constants below (COLLECTION, THUMBS_DIR) — nothing else.
"""

import os
from pathlib import Path

import streamlit as st

# ---- Thursday's one-line swap lives here -----------------------------------
COLLECTION = "filmfinder_dev"
THUMBS_DIR = Path("thumbs/dev")
# -----------------------------------------------------------------------------

CHIPS = ["corner kick", "goalkeeper save", "shot on goal",
         "throw-in", "celebration", "tackle in the box"]
SEEK_BUILDUP_S = 3  # land a beat before the moment


def load_settings():
    """Streamlit secrets (deployed) win; fall back to .env (local)."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    for name in ("QDRANT_URL", "QDRANT_API_KEY", "VIDEO_ID"):
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


def run_search(find_moments, query: str):
    try:
        parsed, moments = find_moments(query, collection=COLLECTION)
        return parsed, moments, None
    except Exception as e:
        return None, [], f"Search hiccup ({type(e).__name__}) — try again in a moment."


def set_query(q: str):
    st.session_state.query_input = q


def jump_to(t: int):
    st.session_state.seek_t = int(t)


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

# ---- results ------------------------------------------------------------------
if not query:
    st.info("Search anything you'd scrub the timeline for — or tap a suggestion above.")
else:
    find_moments, mmss = engine()
    with st.spinner(f'Searching for "{query}"...'):
        parsed, moments, error = run_search(find_moments, query)

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

        for row_start in range(0, len(moments), 3):
            cols = st.columns(3)
            for col, m in zip(cols, moments[row_start: row_start + 3]):
                with col:
                    thumb = THUMBS_DIR / m["frame"]
                    if thumb.exists():
                        st.image(str(thumb), use_container_width=True)
                    st.markdown(f"**{mmss(m['t'])}**  \n{m['description']}")
                    st.button(f"▶ Jump to {mmss(m['t'])}", key=f"jump_{m['frame']}",
                              on_click=jump_to, args=(m["t"],),
                              use_container_width=True)
