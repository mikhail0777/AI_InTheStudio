# Open-vocabulary video search migration

## Phase 1 audit

### Scope and acceptance criteria

This phase documents the existing system and defines an incremental target architecture. It
does not change runtime behavior. It is complete when the current data flow, reusable parts,
person-specific assumptions, target interfaces, storage/API/UI migrations, risks, performance
strategy, test strategy, and the first two vertical slices are explicit and traceable to the
repository. The existing backend suite and frontend production build must still pass.

## Current architecture

The application is a local, single-user FastAPI and React application backed by SQLite.

1. `TargetForm.tsx` collects one free-text person description, a video, and optional DJI SRT.
2. `endpoints.py` creates a session, streams uploads into a generated session directory, and
   queues one analysis run. Upload filenames never become filesystem paths.
3. `analysis_worker.py` provides a durable SQLite queue and a single cooperative worker with
   pause, resume, cancellation, restart recovery, and an operating-system lock.
4. `SearchPlanAgent` applies clothing-oriented regular expressions and produces a person
   search strategy.
5. `AgenticLoopManager` samples a broad pass, uses positive detections to schedule a focused
   pass, runs `PersonDetector`, associates detections with `PersonTracker`, evaluates each
   track with `AppearanceAnalyzer`, attaches aircraft telemetry, and generates a report.
6. `PersonDetector` runs local YOLO instance segmentation over full frames and overlapping
   tiles. It retains only COCO person and backpack classes and derives approximate upper/lower
   color evidence from masks.
7. `PersonTracker` associates boxes using IoU and a time gap. `AppearanceAnalyzer` aggregates
   separated observations, gates weak person evidence, and classifies clothing-oriented
   matches.
8. SQLite stores sessions, runs, planned/sampled frames, detections, tracks, logs, and
   telemetry. JSON payload columns preserve fields not represented by legacy columns.
9. The React UI polls run status and renders person track cards, source video, telemetry,
   explanations, feedback controls, and a SAR-oriented report.

The baseline at the start of this migration is 43 passing Python tests and a passing
TypeScript/Vite production build. The suite emits Pydantic v2 deprecation warnings for
`.dict()` calls; those should be removed during schema migration.

## Reusable components

- Safe streamed upload handling, video inspection, generated storage names, and size limits.
- Durable sessions, analysis runs, progress logs, cooperative cancellation, and restart
  behavior.
- Frame decoding and timestamp calculation, after extraction behind an indexing interface.
- Full-frame plus tiled YOLO inference as one optional proposal provider.
- Detection provenance, evidence crops, quality metadata, human feedback, and review history.
- SRT parsing and timestamp-to-aircraft-position lookup.
- Local evidence serving protections and report escaping/path validation.
- React polling, source-video seeking, evidence review, and feedback interaction patterns.
- Existing person/clothing analysis as an optional specialized evidence provider.

## Assumptions that must be removed

| Area | Current assumption | Required replacement |
| --- | --- | --- |
| Query | Text describes one person's clothing | Structured entities, attributes, actions, relations, sequences, and negation |
| Detection | Searchable objects are YOLO people/backpacks | Pluggable fixed-class detection plus open-vocabulary grounding |
| Sampling | Person detections trigger denser sampling | Query-independent reusable keyframes, scenes, and clips |
| Tracking | Every track is a person | Typed entity tracks and event groups |
| Evidence | Upper/lower body colors dominate | Generic localized evidence with component scores and required gates |
| Time | A track is enough to describe a result | Clip-level temporal evidence for motion-dependent actions |
| Storage | A session owns one analysis/search | A video index supports many searches and versioned models |
| Results | Results are person `TrackResult` objects | Generic event results containing participating entity tracks |
| UI/report | People, sightings, and SAR wording | Targets, events, matches, entity types, clips, and model provenance |

## Target architecture

The target pipeline is:

`SearchQuery -> VideoIndex -> SemanticRetriever -> Grounding/Tracking -> ClipVerifier -> EvidenceRanker`

### Domain contracts

Introduce provider-neutral Pydantic models:

- `SearchQuery`: original text, parsed entities, attributes, actions, relationships, event
  steps, negative constraints, required evidence IDs, optional evidence IDs, parser
  provenance, and processing mode.
- `EntityMention`: query-local ID, type/name, attributes, quantity, required flag, and
  negative flag.
- `RelationshipConstraint` and `ActionConstraint`: participant IDs, predicate, temporal
  requirements, required flag, and confidence.
- `IndexedFrame` and `IndexedClip`: timestamps, scene, paths, embedding references, quality,
  and index/model versions.
- `EntityDetection` and `EntityTrack`: generic label, box/mask, confidence, visibility,
  attributes, provenance, and observations.
- `EvidenceAssessment`: criterion ID and kind, assessment (`supported`, `conflicting`,
  `missing`, `uncertain`, or `unsupported`), score, timestamps, entity IDs, paths, and model.
- `SearchResult`: event interval, representative frame, playable clip, participants,
  assessments, component scores, gated classification, explanation, provenance, and human
  feedback.

Retain compatibility aliases/adapters for `TargetConfiguration` and `TrackResult` until the
frontend, reports, and stored historical data no longer depend on them.

### Replaceable model interfaces

All providers expose model name, immutable version/revision, device, input assumptions, and
batch methods. They must not write directly to the database.

- `QueryParser.parse(text) -> SearchQuery`
- `SceneSampler.plan(video) -> scenes/keyframes/clips`
- `EmbeddingProvider.embed_images/embed_text -> vectors`
- `DetectionProvider.detect(frames, vocabulary?) -> EntityDetection[]`
- `GroundingProvider.ground(frames, phrases) -> EntityDetection[]`
- `SegmentationProvider.segment(frames, prompts) -> masks`
- `TrackingProvider.update/finalize -> EntityTrack[]`
- `ClipVerifier.verify(query, clip, tracks) -> EvidenceAssessment[]`
- `RankingPolicy.rank(query, evidence) -> SearchResult`

Initial implementations remain local and configurable. YOLO stays available as a fast
fixed-class proposal provider. New model downloads and dependencies must be explicit,
version-pinned, cached locally, and licensed for the intended deployment. No footage is sent
to a hosted service by default.

## Storage migration

Use additive migrations and leave legacy tables readable.

- `media_assets`: content hash, canonical local path, metadata, upload/session association.
- `video_indexes`: media ID, status, mode, sampler/index version, model manifest, timestamps,
  error, and uniqueness key derived from media hash plus index configuration.
- `scenes`, `indexed_frames`, and `indexed_clips`: reusable temporal structure and artifact
  paths.
- `embeddings`: owner kind/ID, provider/version, dimension, normalized vector blob, and
  metadata. SQLite brute-force cosine search is sufficient for the first slice; isolate a
  vector-store interface before adopting an extension.
- `entity_detections` and `entity_tracks`: generic localized observations and associations.
- `searches`: session/index/query, status, parser/version, processing mode, and timing.
- `search_candidates`: retrieval scores and shortlist audit data.
- `search_results`: event interval, classification, overall/component scores, explanation,
  provenance, feedback, and JSON payload.
- `result_entities` and `evidence_assessments`: normalized result participants and evidence.

Indexes and artifacts are immutable by version. A changed model or sampling configuration
creates a new index rather than silently mixing representations.

## API migration

Add generic endpoints while retaining existing routes through adapters during migration:

- `POST /api/media` and `GET /api/media/{id}`
- `POST /api/media/{id}/indexes`, `GET /api/indexes/{id}/status`
- `POST /api/indexes/{id}/searches`, `GET /api/searches/{id}/status`
- `GET /api/searches/{id}/results`
- `POST /api/searches/{id}/results/{result_id}/feedback`
- `GET /api/results/{result_id}/clip` and evidence artifact routes

Session creation can initially orchestrate these resources so current clients continue to
work. Responses must use entity/event counts and expose stage-specific progress, cache hits,
model provenance, coverage, and honest no-match language.

## UI migration

- Change the prompt to "What would you like to find in this video?" and show broad examples.
- Separate reusable indexing progress from query-specific retrieval/verification progress.
- Replace person cards with event cards showing intervals, clips, highlighted participants,
  evidence assessments, classifications, and component scores.
- Add filters for confidence/classification, entity type, and time.
- Preserve source-video seeking, telemetry context, feedback, cancellation, and reports.
- Continue to render old person results through a compatibility mapper during rollout.

## Performance and caching strategy

- Hash uploaded bytes while streaming and reuse compatible completed indexes for identical
  media; never trust filenames for identity.
- Detect scene changes and sample keyframes adaptively, retaining coverage bounds.
- Batch frame decoding and model inference; use CUDA when available and deterministic CPU
  fallback with smaller batches.
- Compute frame/clip embeddings once and search them cheaply for every query.
- Run grounding on the retrieval shortlist and expensive clip verification only on grouped
  candidate windows.
- Merge overlapping windows and entity tracks before verification and presentation.
- Store stage timings, frame/clip counts, cache hit state, devices, and model revisions.
- `fast`, `balanced`, and `thorough` modes select documented sampling density, shortlist size,
  grounding resolution, and verifier budget; required evidence gates never weaken by mode.

## Evidence and ranking policy

Every required query criterion receives an independent assessment. A result cannot be a
strong or possible match when a required entity, relationship, or temporal action is missing
or conflicting. Unknown and unsupported are distinct. Ranking combines entity presence,
attribute agreement, action agreement, relationship agreement, temporal consistency,
localization quality, visibility, semantic similarity, and verifier confidence only after
the required-evidence gate. Repeated adjacent frames do not manufacture independent support.

Valid classifications are `strong_match`, `possible_match`, `unlikely_match`,
`insufficient_visibility`, and `unsupported_query`. Empty results use: "No matching event was
found in the analyzed frames." They do not claim the event is absent from the entire video.

## Migration phases and acceptance criteria

### Phase 2: generic schemas and provider contracts

Add the domain models, protocols, serialization, compatibility adapters, and additive schema
migrations. Existing clothing requests and historical results remain readable. Tests cover
multi-entity queries, relationships, temporal actions, negation, required/optional evidence,
and migration idempotence.

### Phase 3: reusable video indexing

Create content-addressed media/index records, adaptive keyframes, scene boundaries, clip
windows, artifact manifests, and cache reuse. Empty/corrupt inputs fail honestly. Tests prove
that a second search does not decode/index the same compatible video again and that CPU mode
works.

### Phase 4: semantic frame and clip retrieval

Integrate a local embedding provider behind the interface, batch indexing, cosine retrieval,
query-specific candidates, and retrieval metrics. Real inference must demonstrate retrieval
on reviewable non-synthetic footage or a documented redistribution-safe evaluation fixture.

### Phase 5: yellow-car vertical slice

Add generic localization, color evidence, tracking/deduplication, event results, clips, API,
and UI rendering. Acceptance requires real inference for "a yellow car" with timestamps,
localized evidence, false-positive review, cold/repeat timing, and model provenance. Keyword,
filename, and hardcoded-result shortcuts are forbidden.

### Phase 6: grounding, tracking, and clip verification

Add open-vocabulary grounding and generic tracking, group candidate windows, and implement
structured clip-verifier evidence. Unit tests include unrelated co-occurring objects that
must not become an interaction.

### Phase 7: pushing-stroller vertical slice

Support "a person pushing a stroller" through the same index and result pipeline. Required
entity, relationship, and temporal-action gates must pass on real multi-frame evidence. Report
timestamps, localization, false positives, cold/repeat timing, models, and limitations.

### Phase 8: broad query generalization

Generalize parser, grounding, verification, and ranking to multiple entities, attributes,
relationships, actions, event sequences, and negative constraints. Preserve clothing search
regressions through the generic path.

### Phase 9: performance modes and UI completion

Implement and benchmark fast/balanced/thorough configurations, batching, GPU/CPU selection,
filters, progress, highlighted entities, clip playback, and generic reporting. Record p50/p95
stage timings and repeat-search latency.

### Phase 10: evaluation and hardening

Add integration/evaluation coverage for every scenario in the product specification,
including corrupt/empty media, occlusion, lighting, angles, distance, duplicates, unsupported
evidence, and CPU-only runs. Publish reproducible recall, false-positive, localization,
ranking, cold-time, and warm-time reports without claiming unmeasured accuracy.

## First implementation slices

The first functional slice is "a yellow car": one reusable index, semantic retrieval,
localized vehicle/color evidence, track/event deduplication, reviewable clip, and generic UI
result. The immediately following slice is "a person pushing a stroller" using the same
tables, APIs, providers, and ranking gates with multi-frame action evidence. These are not
separate applications or hardcoded query handlers.

## Risks and dependencies

- Pretrained model weights add disk, memory, download, licensing, and supply-chain concerns.
  Pin revisions and hashes and document weight licenses before adoption.
- GPU acceleration differs by CUDA/driver availability; all phases need bounded CPU behavior.
- Video-text similarity is retrieval, not proof. It must never bypass localization and
  required-evidence verification.
- General grounding and VLM outputs are not intrinsically calibrated; labeled evaluation and
  human review remain required.
- Action recognition needs adequate temporal resolution and may be unsupported for distant,
  occluded, or low-frame-rate footage.
- Content hashes and cached artifacts can contain sensitive-derived data; local retention and
  deletion must include indexes, crops, clips, embeddings, and reports.
- Current SQLite/single-worker design is suitable for a local workstation, not concurrent
  multi-tenant deployment. Provider and repository boundaries should permit later replacement.
- Existing sample drone videos may not contain the two required milestone events. A suitable
  licensed evaluation video or user-provided footage is necessary to validate real recall and
  false positives; synthetic fixtures remain useful only for deterministic integration tests.

## Phase review checklist

Before every phase commit: run affected unit/integration tests and the full regression suite,
build the frontend when touched, run `git diff --check`, inspect the diff for secrets/path
exposure/unintended files, record real-inference evidence when required, and do not commit a
known failing phase.
