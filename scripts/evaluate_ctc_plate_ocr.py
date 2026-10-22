"""Evaluate a CRNN/CTC plate reader with auditable top-k sequence candidates."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time

import torch
from torch.utils.data import DataLoader


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evaluation_metrics import levenshtein, wilson_interval
from scripts.train_ctc_plate_ocr import (
    PlateCRNN, PlateDataset, collect_samples, collate, sha256,
)


def logadd(left: float, right: float) -> float:
    if left == -math.inf:
        return right
    if right == -math.inf:
        return left
    high, low = max(left, right), min(left, right)
    return high + math.log1p(math.exp(low - high))


def ctc_beam_candidates(
    log_probs: torch.Tensor, alphabet: list[str], beam_width: int = 25, top_k: int = 5,
) -> list[dict]:
    states: dict[tuple[tuple[int, ...], int], float] = {((), 0): 0.0}
    for timestep in log_probs.tolist():
        token_ids = sorted(range(len(timestep)), key=timestep.__getitem__, reverse=True)[: min(12, len(timestep))]
        next_states: dict[tuple[tuple[int, ...], int], float] = {}
        for (prefix, previous), score in states.items():
            for token in token_ids:
                candidate = prefix if token == 0 or token == previous else prefix + (token,)
                state = (candidate, token)
                next_states[state] = logadd(next_states.get(state, -math.inf), score + timestep[token])
        states = dict(sorted(next_states.items(), key=lambda item: item[1], reverse=True)[:beam_width])
    sequences: dict[tuple[int, ...], float] = {}
    for (prefix, _), score in states.items():
        sequences[prefix] = logadd(sequences.get(prefix, -math.inf), score)
    ranked = sorted(sequences.items(), key=lambda item: item[1], reverse=True)[:top_k]
    return [
        {"text": "".join(alphabet[token - 1] for token in tokens), "log_score": score}
        for tokens, score in ranked
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--split", choices=["valid", "test"], required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--beam-width", type=int, default=25)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    checkpoint = torch.load(args.model, map_location="cpu", weights_only=True)
    alphabet = checkpoint["alphabet"]
    model = PlateCRNN(len(alphabet)); model.load_state_dict(checkpoint["state_dict"]); model.eval()
    samples = collect_samples(args.dataset, args.split, alphabet)
    loader = DataLoader(
        PlateDataset(samples, alphabet, False), batch_size=16,
        shuffle=False, collate_fn=collate, num_workers=0,
    )
    rows = []; started = time.perf_counter()
    with torch.inference_mode():
        offset = 0
        for images, _, _, expected in loader:
            predictions = model(images).transpose(0, 1)
            for index, sequence in enumerate(expected):
                candidates = ctc_beam_candidates(
                    predictions[index], alphabet, args.beam_width, args.top_k,
                )
                rows.append({
                    "file": samples[offset + index].image.name,
                    "expected": sequence,
                    "candidates": candidates,
                })
            offset += len(expected)
    elapsed = time.perf_counter() - started
    exact = sum(row["candidates"][0]["text"] == row["expected"] for row in rows)
    top3 = sum(row["expected"] in [item["text"] for item in row["candidates"][:3]] for row in rows)
    topk = sum(row["expected"] in [item["text"] for item in row["candidates"]] for row in rows)
    characters = sum(len(row["expected"]) for row in rows)
    edits = sum(levenshtein(row["expected"], row["candidates"][0]["text"]) for row in rows)
    report = {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(args.dataset.resolve()), "split": args.split,
        "model": str(args.model.resolve()), "model_sha256": sha256(args.model),
        "decoder": {"type": "CTC beam search", "beam_width": args.beam_width, "top_k": args.top_k},
        "metrics": {
            "plates": len(rows), "exact_matches": exact,
            "exact_plate_accuracy": exact / len(rows) if rows else 0.0,
            "exact_plate_accuracy_wilson_95": wilson_interval(exact, len(rows)),
            "top_3_matches": top3, "top_3_accuracy": top3 / len(rows) if rows else 0.0,
            "top_k_matches": topk, "top_k_accuracy": topk / len(rows) if rows else 0.0,
            "character_edits": edits, "ground_truth_characters": characters,
            "character_accuracy": 1.0 - edits / characters if characters else 0.0,
        },
        "runtime": {"device": "cpu", "elapsed_seconds": elapsed}, "rows": rows,
        "limitations": [
            "Cropped single-row plates are a proxy, not dealership-video vehicle events.",
            "The previously inspected 37-plate split is a development regression set, not a fresh final test.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "metrics": report["metrics"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
