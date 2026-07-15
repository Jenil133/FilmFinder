# FilmFinder
Ctrl+F for game film: type plain English, jump to the exact moments in match video

> 🚧 **Under construction** — hackathon build in progress (July 2026).

**Stack:** ffmpeg frames → Gemini Flash captions → FastEmbed → Qdrant → Streamlit.

## Quick start (dev)

```bash
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in your keys
python verify_keys.py       # every key verified with a real call
```

Pipeline (Phase 1 kill-test):

```bash
python extract_frames.py --video match01.mp4 --start 00:20:00 --duration 720 --out frames/dev
python captioner.py --frames-dir frames/dev --out captions_dev.jsonl
python indexer.py --captions captions_dev.jsonl --collection filmfinder_dev
python killtest.py
streamlit run app.py
```

Footage license: see [ATTRIBUTION.md](ATTRIBUTION.md).
