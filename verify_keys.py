"""Verify every API key with a REAL call (Phase 1 acceptance criterion:
"created" is not "verified").

Usage:
    python verify_keys.py
"""

import os
import sys

from dotenv import load_dotenv


def check_gemini() -> str:
    from google import genai
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        return "MISSING (set GOOGLE_API_KEY in .env)"
    client = genai.Client(api_key=key)
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
    resp = client.models.generate_content(model=model, contents="Reply with the single word: pong")
    return f"OK — {model} replied: {resp.text.strip()[:40]!r}"


def check_qdrant() -> str:
    from qdrant_client import QdrantClient
    url, key = os.environ.get("QDRANT_URL"), os.environ.get("QDRANT_API_KEY")
    if not url or not key:
        return "MISSING (set QDRANT_URL and QDRANT_API_KEY in .env)"
    client = QdrantClient(url=url, api_key=key, timeout=30)
    cols = [c.name for c in client.get_collections().collections]
    return f"OK — cluster reachable, collections: {cols or '(none yet)'}"


def check_groq() -> str:
    from groq import Groq
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return "MISSING (set GROQ_API_KEY in .env)"
    client = Groq(api_key=key)
    resp = client.chat.completions.create(
        model="openai/gpt-oss-20b",  # llama-3.1-8b-instant shuts down 08/16/26
        messages=[{"role": "user", "content": "Reply with the single word: pong"}],
        max_tokens=100,  # reasoning model: leave room for reasoning + reply
    )
    return f"OK — replied: {resp.choices[0].message.content.strip()[:40]!r}"


def main():
    load_dotenv()
    checks = [("Gemini (google-genai)", check_gemini),
              ("Qdrant Cloud", check_qdrant),
              ("Groq", check_groq)]
    failures = 0
    for name, fn in checks:
        try:
            status = fn()
        except Exception as e:
            status = f"FAIL — {type(e).__name__}: {e}"
        ok = status.startswith("OK")
        if not ok:
            failures += 1
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {status}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
