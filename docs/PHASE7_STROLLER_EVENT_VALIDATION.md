# Phase 7: person pushing a stroller

## Scope and acceptance criteria

This phase completes the second vertical slice on the same query, index, retrieval,
localization, tracking, evidence, result, API, report, and UI pipeline used by color-qualified
cars.

Acceptance requires:

- `person`, `stroller`, and `person.pushing.stroller` remain separate required criteria.
- The query routes to generic event search while established person/backpack searches continue
  to work during their incremental migration.
- YOLO person detections and OWLv2 stroller grounding are combined into paired event candidates.
- Pushing requires at least two sampled moments with person-stroller box contact and coordinated
  motion; one frame, mere proximity, or unrelated co-visible objects cannot support the action.
- Fragmented secondary tracks do not duplicate one actor/event.
- One result contains both entity tracks, an annotated frame, playable clip, timestamps,
  structured evidence, component scores, explanation, and complete model provenance.
- Real inference retrieves the correct event and review does not identify a promoted false event.
- Existing API, UI, feedback, reporting, cancellation, telemetry, and person searches regress cleanly.

## Automated verification

Coverage includes generic-worker dispatch, missing required entities, unrelated objects,
stationary nearby objects, single-frame action rejection, coordinated multi-frame motion,
track-fragment deduplication, joint-frame/clip materialization, result persistence, feedback,
and existing regressions.

The final backend and frontend verification totals are recorded immediately before commit.

## Real inference and calibration

Source: `DJI_0179.MP4`, 3840x2160, 39.106 seconds, CPU execution, cached reusable index.

The first complete run took 428.062 seconds and retrieved the real stroller sequence, but it
incorrectly promoted six pairings because global camera motion plus broad proximity allowed
nearby pedestrians to look coordinated. That run failed acceptance and was not used as the
final result.

The verifier was corrected to require repeated overlap between the person and stroller/handle
box, coordinated motion, and event deduplication. The final complete run produced:

- Processing time after indexing: 288.705 seconds.
- Results: 1 strong match, 3 insufficient-visibility candidates, 4 unlikely matches.
- Correct strong event interval: 20.522-39.106 seconds.
- Best representative frame: 30.030 seconds.
- Person track: 17 observations from 23.023-39.072 seconds.
- Stroller track: 17 observations from 22.022-39.072 seconds.
- Supported contact/co-motion evidence: 15 sampled moments from 23.02-37.04 seconds.
- Promoted false positives after visual review: 0. Nearby pedestrian pairings were not promoted.
- Reviewable evidence: joint colored boxes, entity crops, an 18.584-second clip, explanations,
  component scores, and provenance for SigLIP, YOLO, OWLv2, and the deterministic verifier.

The representative frame visibly places the detected person immediately behind and overlapping
the stroller box. Review of the sequence is still required: geometry and co-motion support the
action but do not provide identity certainty or fine-grained hand-pose recognition.

## Models and known limitations

- Retrieval: `google/siglip-base-patch16-224` at revision
  `7fd15f0689c79d79e38b1c2e2e2370a7bf2761ed`.
- Person localization: local `yolo11s-seg.pt`, SHA-256
  `1caa81c0195412efa411b632bcfb8c184939dddb6ae41f6a80c41b211ff257c3`.
- Stroller grounding: `google/owlv2-base-patch16-ensemble` at revision
  `410d70ced26e95c344915c2f10f4ecf967f2cde4`.
- Temporal verification: local multi-frame geometry verifier version 1.
- CPU latency remains high because grounding detections are not yet cached in the reusable
  index. Detection caching and mode-specific shortlist sizes belong to Phase 9.
- Fast camera motion can still fragment tracks. Fine hand contact, pose, and causal intent are
  not established; the classification must remain human-reviewable.

The combined initial milestone supports both required query shapes through the same pipeline.
The supplied footage contains a real stroller event but no visually confirmed yellow car, so a
labeled real positive yellow-car recall measurement remains outstanding; Phase 5 documented
real yellow-negative behavior and a real red-car positive control without fabricating a claim.
