"""Run a reproducible real-footage semantic retrieval smoke evaluation."""
import argparse
import json
from pathlib import Path
import time

from app import database
from app.services.semantic_retrieval import SemanticRetrievalService
from app.services.video_indexer import VideoIndexer
from app.services.video_service import VideoService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video")
    parser.add_argument("queries", nargs="+")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--output")
    args = parser.parse_args()
    database.init_db()
    metadata = VideoService.inspect_video(str(Path(args.video).resolve()))
    index_start = time.perf_counter()
    index = VideoIndexer().build_or_reuse(metadata, mode="balanced")
    index_seconds = time.perf_counter() - index_start
    retrieval = SemanticRetrievalService()
    embedding_start = time.perf_counter()
    embedded = retrieval.index_frames(index.index_id)
    clips_embedded = retrieval.index_clips(index.index_id)
    embedding_seconds = time.perf_counter() - embedding_start
    results = []
    for query in args.queries:
        started = time.perf_counter()
        candidates = retrieval.retrieve(index.index_id, query, limit=args.limit)
        results.append({
            "query": query, "retrieval_seconds": time.perf_counter() - started,
            "candidates": [item.model_dump(mode="json") for item in candidates],
        })
    repeat_start = time.perf_counter()
    repeat = VideoIndexer().build_or_reuse(metadata, mode="balanced")
    repeat_seconds = time.perf_counter() - repeat_start
    report = {
        "video": metadata.model_dump(mode="json"), "index_id": index.index_id,
        "index_cache_hit": index.cache_hit, "index_seconds": index_seconds,
        "frames_embedded": embedded, "clips_embedded": clips_embedded,
        "embedding_seconds": embedding_seconds,
        "repeat_index_cache_hit": repeat.cache_hit, "repeat_index_seconds": repeat_seconds,
        "queries": results,
    }
    rendered = json.dumps(report, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
