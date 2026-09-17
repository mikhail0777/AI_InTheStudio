# Phase 8: broad query generalization

## Scope and acceptance criteria

This phase replaces worker-level pipeline selection with one unified search entrypoint while
retaining person/clothing analysis as an optional specialist provider. Every completed search
must publish the provider-neutral `SearchQuery` and `SearchResult` contract without removing
legacy track, feedback, or report compatibility.

Acceptance requires:

- quantities require distinct entity tracks;
- positive and negative entities, per-entity colors, visible attributes, relationships,
  actions, and ordered event steps remain explicit evidence criteria;
- carrying and pushing require repeated contact plus coordinated motion;
- negated actions and relationships invert only established evidence, while uncertain evidence
  remains uncertain;
- event order is supported only when timestamped action evidence establishes that order;
- person/clothing and backpack searches retain their established verifier and publish adapted
  generic results through the same worker;
- real inference exercises the unified generic quantity path and visual review confirms distinct
  localized people;
- existing APIs, reports, feedback, cancellation, telemetry, and earlier vertical slices regress
  cleanly.

## Implementation

- `UnifiedSearchManager` is the only analysis-worker entrypoint. It routes replaceable providers
  and adapts specialist person tracks into generic persisted searches/results.
- The parser represents word/digit quantities, excluded entities, colors and visible attributes,
  negative actions/relationships, and `then`-ordered event steps. Single-person appearance and
  backpack compatibility searches retain the specialist; quantities and other interactions use
  generic localization.
- Event ranking expands quantity slots, rejects reuse of one track for multiple slots, evaluates
  attributes on their owning entity, records excluded-entity evidence, and preserves conservative
  classifications.
- Multi-frame verification now covers carrying and negative constraints. It does not claim event
  order when action timestamps overlap or are absent.
- Legacy sessions expose generic `/results` and status query/count fields while legacy feedback and
  report behavior remain available.

## Real inference

Corrected acceptance run:

| Input | Query | Device | Elapsed | Outcome |
|---|---|---:|---:|---|
| `DJI_0178.MP4`, 3840x2160, 2.135 s | `two people` | CPU | 17.312 s | 4 strong joint candidates |

The run used the unified entrypoint, cached/reusable SigLIP indexing, YOLO instance segmentation,
distinct-track quantity ranking, annotated frames, and playable clips. Visual review of the top
frame confirmed two different people on opposite sidewalks; it was not a duplicated box. Model
provenance recorded the pinned SigLIP revision/hash, YOLO weight hash, and deterministic geometry
verifier.

An initial full `DJI_0179.MP4` run exposed that `two people` was incorrectly routed to the legacy
person specialist. It completed in 1971.316 seconds and was rejected as Phase 8 acceptance evidence.
The routing defect was fixed and regression-tested before the corrected run above. That timing is
retained as a Phase 9 performance baseline rather than presented as acceptable latency.

## Verification and review

- Backend: `python -m unittest discover -s tests -v`
- Frontend: `npm.cmd run build`
- Focused tests cover unified worker publication, quantity routing and distinct tracks, secondary
  entity colors, excluded entities, carrying, negative relationships, event ordering, and legacy
  compatibility.
- Security review retained query-length validation, bounded tracks/event combinations, escaped
  reports, session-scoped evidence paths, offline model inference, and no user-controlled command or
  path construction.

Known limitations remain explicit: visible attributes without a specialized verifier are uncertain;
the deterministic sequence verifier cannot segment overlapping action intervals; generic tracking
can fragment identities; and dense 4K CPU localization needs the mode-aware optimization scheduled
for Phase 9.
