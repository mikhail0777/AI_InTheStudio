# Phase 6: grounding, tracking, and multi-frame reasoning

## Scope and acceptance criteria

This phase adds replaceable phrase grounding for entities outside YOLO's class list,
motion-tolerant entity tracking, phrase-aware duplicate suppression, and conservative
multi-frame geometry/motion evidence. It extends the shared semantic retrieval pipeline and
does not create a separate program.

Acceptance requires:

- Fixed-taxonomy entities route to YOLO while unsupported phrases route to OWLv2.
- Runtime is offline-only; the OWLv2 revision and safetensor hash are verified at install/load.
- Grounded evidence contains reviewable boxes, crops, timestamps, scores, and provenance.
- Overlapping phrase boxes collapse before tracking.
- Tracks tolerate moderate motion between sampled frames without merging distant entities.
- Repeated proximity can support a spatial relationship; unrelated co-visible objects conflict.
- A temporal action cannot be supported from one isolated frame.
- Required action/relationship evidence that is not supported prevents a strong result.
- Existing search, feedback, reporting, cancellation, telemetry, and person behavior regress cleanly.

## Implementation

- `Owlv2GroundingProvider` uses `google/owlv2-base-patch16-ensemble` only for vocabulary not
  supported by the fast local YOLO provider. OWLv2 supplies bounding boxes, not masks; any
  color distribution from an inset box is explicitly approximate.
- Phrase-aware non-maximum suppression removes duplicate boxes in each frame.
- Tracking uses both IoU and size-normalized center proximity across sampled frames.
- `MultiFrameEvidenceVerifier` produces structured supported, conflicting, missing, or
  uncertain action/relationship evidence. It supports repeated spatial association and a
  conservative displacement signal for `running`; it intentionally leaves interactions such
  as pushing uncertain until the event-level Phase 7 verifier associates both tracks.

## Real inference

Two 3840x2160 indexed frames from `DJI_0179.MP4` at 22.022 s and 23.023 s were selected because
the original footage visibly contains a person with a stroller in the lower-right corner.

- CPU grounding time: 15.422 s for two frames after model load.
- Default threshold plus phrase NMS: four detections.
- Tracking time was included in a 15.801 s repeat run: two two-observation tracks.
- Correct stroller track: observations at 22.022 s and 23.023 s; maximum confidence 0.4126.
- False-positive track: a small storefront/sign region at both timestamps; maximum confidence
  0.1595. It remains a candidate and is not evidence of pushing without person association and
  temporal verification.
- Visual review confirmed the highest-scoring crops show the stroller and its wheels. Duplicate
  overlapping stroller boxes were removed.

This establishes real open-vocabulary grounding and track formation. It does not yet claim
that `person pushing a stroller` is a supported event; that complete vertical slice, including
person-stroller association, temporal action gating, event clips, and measured false positives,
is Phase 7.

## Model provenance and limitations

- Model: `google/owlv2-base-patch16-ensemble`
- Immutable revision: `410d70ced26e95c344915c2f10f4ecf967f2cde4`
- Safetensor SHA-256: `e1e130b9e404cf91a75ad45644c1da9d7fa5284085eecc864266a6923efb99e7`
- License: Apache-2.0
- Size: approximately 620 MB
- CPU inference is usable but slow on 4K frames. The provider batches and runs only on semantic
  candidates for phrases YOLO cannot localize.
- OWLv2 boxes can include background and small visual lookalikes. Event verification must use
  multiple entities and timestamps rather than grounding confidence alone.
