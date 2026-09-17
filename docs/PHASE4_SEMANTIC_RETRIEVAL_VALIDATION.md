# Phase 4 semantic retrieval validation

## Scope and acceptance criteria

Phase 4 adds a pinned local image/text embedding provider, persistent normalized frame and
aggregated clip embeddings, cosine candidate retrieval, auditable candidate rows, CPU fallback, and an
offline evaluation command. It is complete when deterministic provider tests pass, the full
regression suite and frontend build pass, and real model inference retrieves reviewable
content from non-synthetic footage with model provenance and cold/warm timings.

## Model provenance

- Provider: Hugging Face Transformers, offline runtime
- Model: `google/siglip-base-patch16-224`
- Revision: `7fd15f0689c79d79e38b1c2e2e2370a7bf2761ed`
- Safetensor SHA-256: `2c63cb7d1f2e95ba501893cbb8faeb4ea9a3af295498d35097126228659c2af8`
- Model license declared by its repository: Apache-2.0
- Device used: CPU (CUDA was unavailable)

The runtime uses `local_files_only=True` and `use_safetensors=True`. Model downloading remains
an explicit `backend/download_models.py` installation step rather than an inference side
effect.

## Real-footage smoke evaluation

Command:

```powershell
$env:PYTHONPATH='backend'
$env:AIEYE_DATA_DIR='backend/data/validation/open-vocab-phase4'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
python backend/evaluate_semantic_retrieval.py videos/DJI_0179.MP4 `
  'a person walking on a road' 'a road with cars' `
  'trees and grass viewed from above' --limit 5
```

Input facts:

- Real DJI video, 3840 x 2160, H.264, 39.106 seconds, 1,172 frames, 434.31 MB.
- Balanced indexing produced 41 keyframes, 41 frame embeddings, and 41 aggregated clip embeddings.
- Cold index: 28.375 seconds.
- CPU embedding: 13.453 seconds.
- Compatible repeat index lookup: 0.418 seconds and reported a cache hit.
- Query retrieval after indexing: 0.046 to 0.109 seconds for five candidates.

Manual review:

- `a person walking on a road`: rank 1 at 29.029 seconds. The frame visibly contains several
  pedestrians, including a person crossing the road and people walking on the sidewalk.
- `a road with cars`: rank 1 at 21.021 seconds. The frame visibly contains an urban road with
  moving and parked cars.
- `trees and grass viewed from above`: the footage contains an urban street rather than the
  requested scene. Similarities were negative and are retained as broad candidates, not
  presented as verified matches.

This validates broad semantic retrieval and cache behavior, not event verification or a
calibrated match probability. Required-evidence gating, localization, tracking, and temporal
verification remain later phases. In particular, a high retrieval rank alone must never be
reported as proof that a complete user description is present.
