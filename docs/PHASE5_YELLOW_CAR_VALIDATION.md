# Phase 5: color-qualified car search

## Scope and acceptance criteria

This phase implements the first localized generic vertical slice on the shared application
pipeline: parse `a yellow car`, retrieve semantically relevant indexed frames/clips, localize
cars, evaluate color only inside segmentation masks, deduplicate observations into tracks,
apply required entity and color gates, persist ranked results, and expose annotated frames,
clips, explanations, provenance, reports, and reviewer feedback through the existing API/UI.

Acceptance requires:

- `car` and `yellow` are separate required evidence criteria.
- A car cannot be promoted when yellow evidence conflicts or is missing.
- Adjacent detections are grouped into one track.
- Results persist and round-trip through status, results, feedback, and escaped HTML reports.
- Existing person searches, telemetry, cancellation, feedback, and reports regress cleanly.
- Real inference produces reviewable localization and does not promote visible non-yellow cars.
- At least one real color-qualified car is promoted as a positive control by the same pipeline.

The implementation uses the generic contracts introduced in Phase 2 and the reusable index
and SigLIP retrieval from Phases 3-4. It is not a separate yellow-car program. The detector is
the replaceable generic detection interface backed in this phase by COCO YOLO segmentation.

## Automated verification

- Backend: 65 tests passed before real-inference calibration; the final suite is rerun before
  commit. Phase-specific coverage includes query parsing, masked color localization, unknown
  vocabulary rejection, required-color gating, chromatic highlight/window dilution, adjacent
  observation deduplication, API persistence, reviewer feedback, and report escaping.
- Frontend: TypeScript and the production Vite build passed.
- Synthetic tests establish the exact `yellow` gate without treating those tests as a model
  quality demonstration.

## Real inference results

All runs used CPU inference and repository footage at 3840x2160. Candidate retrieval used
revision-pinned `google/siglip-base-patch16-224`; localization used the pinned local
`yolo11s-seg.pt`. Result images and clips were visually reviewed.

| Query / video | Index state | Time | Outcome | Review |
|---|---:|---:|---|---|
| `a yellow car`, DJI_0178.MP4 (2.135 s) | cold | 50.764 s | 20/20 localized tracks were unlikely matches | Top box was a gray car; strongest displayed yellow support was 0.24%; no false positive |
| `a yellow car`, DJI_0179.MP4 (39.106 s) | cold | 227.607 s | 20/20 localized tracks were unlikely matches | Top box was a white car; top-five yellow support was at most 0.13%; no false positive |
| `a red car`, DJI_0178.MP4 (2.135 s) | cached | 27.379 s after calibration | 1 strong match, 9 unlikely matches | Strong result is the clearly visible red Tesla at 1.001 s, with a mask, annotated frame, and clip |

The initial red-car run localized the correct Tesla but conservatively called 30% masked red
coverage uncertain because windows, highlights, and shadow dilute vehicle body color. The
calibrated gate requires at least 18% raw masked coverage and 30% informative-pixel support.
The same yellow-negative runs were far below both thresholds. Required-color evidence is also
used to prioritize tracks before the configurable result-clip limit.

The supplied recordings do not contain a visually confirmed yellow car. Therefore this phase
does **not** claim a measured positive yellow-car recall value. It demonstrates real negative
yellow behavior and a real positive chromatic-car control, while the exact yellow positive path
is covered by deterministic image/mask tests. A labeled real yellow-car clip remains required
for the combined first-milestone evaluation alongside the stroller slice in Phase 7.

## Provenance and known limits

- SigLIP revision: `7fd15f0689c79d79e38b1c2e2e2370a7bf2761ed`
- SigLIP safetensor SHA-256: `2c63cb7d1f2e95ba501893cbb8faeb4ea9a3af295498d35097126228659c2af8`
- YOLO safetensor SHA-256: `1caa81c0195412efa411b632bcfb8c184939dddb6ae41f6a80c41b211ff257c3`
- CPU remains slow for 4K segmentation. Cached indexing reduced the short validation run, but
  detection and clip encoding still dominate repeat latency.
- COCO localization supports `car`, not make/model grounding; `yellow Tesla` can verify visible
  color and car presence but cannot yet establish Tesla make. Open-vocabulary grounding is the
  next phase.
- IoU tracking may fragment objects under fast camera motion or long sampling gaps.
- Color is illumination-sensitive; uncertain results remain visible for human review.
