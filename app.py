"""FilmFinder — Phase 1 deploy smoke test.

Proves the one Day-1 infrastructure risk: that a YouTube iframe embedded in a
DEPLOYED Streamlit app can seek to an arbitrary timestamp. Phase 2 replaces
this skeleton with the real search UI; the seek mechanic below is reused as-is.
"""

import os

import streamlit as st


def get_setting(name: str, default: str = "") -> str:
    """Streamlit secrets first (deployed), then env/.env (local)."""
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.environ.get(name, default)


try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

st.set_page_config(page_title="FilmFinder", page_icon="🎬", layout="centered")
st.title("🎬 FilmFinder — seek smoke test")
st.caption("Type a number of seconds; the match video should jump straight there. "
           "Muted autoplay is intentional (browser autoplay policy).")

video_id = get_setting("VIDEO_ID")
if not video_id:
    st.warning("No VIDEO_ID configured yet. Set it in .env locally or in the "
               "Streamlit Cloud secrets dashboard, or paste one below to test.")
    video_id = st.text_input("YouTube video id (the part after watch?v=)", value="")

t = st.number_input("Seek to second t", min_value=0, value=0, step=1)
secs = int(t)
target = (f"{secs // 3600}:{secs % 3600 // 60:02d}:{secs % 60:02d}" if secs >= 3600
          else f"{secs // 60}:{secs % 60:02d}")
st.write(f"Target: **{target}**")

if video_id:
    st.iframe(
        f"https://www.youtube.com/embed/{video_id}?start={secs}&autoplay=1&mute=1",
        height=400,
    )
else:
    st.info("Waiting for a video id...")
