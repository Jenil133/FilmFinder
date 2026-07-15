"""FilmFinder indexer.

Embeds captions (action + description) with FastEmbed (BAAI/bge-small-en-v1.5,
384-dim, local, free) and upserts them into a Qdrant Cloud collection with the
full caption JSON + timestamp + frame filename as payload.

Idempotent: point IDs are derived deterministically from the frame filename,
so re-running overwrites the same points instead of duplicating them.

Usage:
    python indexer.py --captions captions_dev.jsonl --collection filmfinder_dev
    python indexer.py --captions captions_dev.jsonl --collection filmfinder_dev --recreate
"""

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
EMBED_DIM = 384
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "filmfinder")


def embed_text(record: dict) -> str:
    """The text that gets embedded — action + description, per the plan."""
    action = record.get("action", "open_play").replace("_", " ")
    return f"{action}: {record.get('description', '')}"


def get_client():
    from qdrant_client import QdrantClient
    url = os.environ.get("QDRANT_URL")
    api_key = os.environ.get("QDRANT_API_KEY")
    if not url or not api_key:
        sys.exit("QDRANT_URL / QDRANT_API_KEY missing — fill .env first (see .env.example)")
    return QdrantClient(url=url, api_key=api_key, timeout=60)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--captions", required=True, help="captions JSONL from captioner.py")
    ap.add_argument("--collection", default="filmfinder_dev")
    ap.add_argument("--recreate", action="store_true", help="drop and recreate the collection")
    ap.add_argument("--batch-size", type=int, default=64)
    args = ap.parse_args()

    load_dotenv()

    from fastembed import TextEmbedding
    from qdrant_client.models import Distance, PointStruct, VectorParams

    records = []
    with Path(args.captions).open() as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    if not records:
        sys.exit(f"No records in {args.captions}")
    print(f"{len(records)} captions loaded from {args.captions}")

    client = get_client()
    if args.recreate and client.collection_exists(args.collection):
        client.delete_collection(args.collection)
        print(f"Dropped collection {args.collection}")
    if not client.collection_exists(args.collection):
        client.create_collection(
            collection_name=args.collection,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
        print(f"Created collection {args.collection} ({EMBED_DIM}-dim cosine)")

    print(f"Embedding with {EMBED_MODEL} (local, downloads model on first run)...")
    model = TextEmbedding(model_name=EMBED_MODEL)
    texts = [embed_text(r) for r in records]
    vectors = list(model.embed(texts, batch_size=64))

    points = [
        PointStruct(
            # id includes the source video: frame numbering restarts per slice,
            # so bare filenames would silently overwrite across sources.
            id=str(uuid.uuid5(NAMESPACE, f"{r.get('video', '')}/{r['frame']}")),
            vector=vec.tolist(),
            payload=r,  # full caption JSON incl. t (timestamp) and frame filename
        )
        for r, vec in zip(records, vectors)
    ]
    for i in range(0, len(points), args.batch_size):
        client.upsert(collection_name=args.collection, points=points[i: i + args.batch_size])
        print(f"  upserted {min(i + args.batch_size, len(points))}/{len(points)}")

    count = client.count(args.collection).count
    print(f"Done — collection {args.collection} now holds {count} points.")


if __name__ == "__main__":
    main()
