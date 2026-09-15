# Production vision architecture for recorded video

## Product claim

The product reviews recorded video from drones, CCTV, body-worn cameras, fixed cameras, and
other sources; finds people; and ranks sightings against an operator's description. It must
never claim identity or absence from incomplete visual
evidence. Operators receive source frames, timestamps, aircraft telemetry, model versions,
and the reason each visible attribute matched, conflicted, or remained unknown.

## Why the current model stops at colors and backpacks

The current YOLO11 segmentation weights use COCO classes. They locate `person` and
`backpack`, but COCO has no classes for button-up shirt, sleeve length, shorts, hair length,
or most person attributes. The application estimates clothing colors inside approximate
body bands. A different trained task is required for semantic clothing attributes.

## Proposed recognition pipeline

1. **Person discovery** — benchmark high-resolution YOLO segmentation against an
   Apache-licensed detector on representative aerial footage. Tune for high person recall,
   including small, stationary, seated, prone, partially occluded, and thermal subjects.
2. **Tracking and deduplication** — associate detections using motion, appearance embeddings,
   and camera movement. Keep one sighting card per likely person while preserving the source
   detections and uncertainty when tracks cannot be joined safely.
3. **Visibility and pose** — determine which body areas are actually visible. Never score
   hair, shoes, sleeves, or lower garments from pixels that do not support that attribute.
4. **Garment segmentation** — segment hair, headwear, upper garment, lower garment, footwear,
   carried bag, and exposed/background areas instead of relying on fixed rectangles.
5. **Multi-label attributes** — classify visible properties across several clear views:
   upper garment type and color; sleeve length; lower garment type and color; backpack/bag;
   hat; footwear; reflective or high-visibility material; and selected rescue-relevant
   accessories. Button-up is included only after the training data supports it.
6. **Text-to-query parser** — convert the operator's description into a structured query,
   including required, optional, negative, and unsupported attributes. Preserve the original
   wording. Observable descriptors are preferred over demographic inference.
7. **Evidence aggregation** — combine calibrated per-view evidence by track. A visible
   conflict differs from an occluded attribute. One sharp image or repeated adjacent frames
   must not manufacture confidence.
8. **Candidate gate** — show only tracks that pass the configured matching policy. Retain all
   person detections in an access-controlled audit record so false negatives can be measured.
9. **Optional second opinion** — use a vision-language model only on quality-gated ambiguous
   crops. Its output is supporting evidence, never the sole alert condition.

## Attribute scope

### First production milestone

- person / no person
- upper garment: shirt, T-shirt, button-up, hoodie, sweater, jacket, coat, vest
- sleeves: sleeveless, short, long
- lower garment: pants, jeans, shorts, skirt
- colors for each segmented garment
- backpack or other carried bag and its color
- hat or helmet
- footwear color when visible
- high-visibility or reflective clothing
- posture: upright, seated/crouched, prone/lying when supported

### Restricted or quality-gated

- Hair color and length may be reported only when the head region has enough pixels and a
  clear view. Aerial rear views will often remain unknown.
- Apparent age and gender should not be used as automatic exclusion gates. They are visually
  ambiguous, introduce bias, and can hide a true rescue candidate. If retained as operator
  notes, they require separate validation and governance.
- Face identity from ordinary drone footage is out of scope. Reference-photo matching would
  be a separate biometric product with different consent, privacy, security, accuracy, and
  procurement requirements.

## Model and platform choices

### Recommended first benchmark

- Keep the current detector as a baseline because it already rejects the known tire failure.
- Add a provider interface so detection, garment segmentation, attributes, and text parsing
  are independent components with recorded model/version provenance.
- Benchmark PaddleX/PP-Human pedestrian attributes as a fast baseline. Its pretrained model
  exposes 26 pedestrian attributes and the Paddle stack is Apache 2.0, but its accuracy on
  high-angle disaster footage must be measured before adoption.
- Train a custom aerial garment/attribute model using data from the intended cameras,
  altitudes, weather, seasons, compression, occlusion, and disaster scenes.

### Role of Roboflow

Roboflow is useful for annotation, dataset versioning, augmentation, training experiments,
and deployment. It is not a replacement for a recognition model. A sensible workflow is to
manage the proprietary aerial dataset in Roboflow, compare candidate model families there,
export a versioned model, and run inference in the product's Canadian deployment environment.
Cloud upload and licensing terms must be reviewed before real rescue footage is sent to a
third party. A self-hosted annotation path should remain available for sensitive footage.

## Accuracy program

No model choice creates “super accuracy” without representative labeled data. Establish a
locked test set before tuning. It must include people and hard negatives: tires, shadows,
mannequins, signs, vegetation, vehicles, empty scenes, groups, small people, stationary
people, prone people, partial views, poor light, smoke, snow, rain, and damaged environments.

Report results by camera, altitude, subject size, pose, visibility, environment, and relevant
demographic groups. Required release metrics include person recall, false person detections
per video hour, target-match recall, candidate precision, attribute precision/recall,
calibration, track fragmentation, time to first finding, processing speed, and operator review
time. Thresholds are selected from these results; UI percentages are not treated as accuracy.

Every release needs regression footage, model/data lineage, reproducible evaluation, drift
monitoring, operator overrides, rollback, and a documented failure mode for degraded inputs.

## Government-ready platform work

The recognition engine is only one part of a shippable service. A Canadian public-sector
deployment also needs threat modeling, authentication and roles, encryption, tenant
isolation, Canadian data residency where required, retention/deletion controls, immutable
audit events, accessibility and bilingual UX, incident response, disaster recovery,
observability, software/model supply-chain records, privacy review, and an operational human
review policy. The applicable department determines whether an Algorithmic Impact Assessment
and Directive on Automated Decision-Making controls apply.

## Delivery sequence

1. Build and label the evaluation set; freeze baseline metrics.
2. Add model-provider interfaces and structured attribute/query schemas.
3. Integrate PP-Human as a benchmark attribute provider behind a feature flag.
4. Compare it with a custom aerial garment/attribute model and choose using held-out results.
5. Add track-level fusion, deduplication, calibrated candidate gating, and evidence display.
6. Pilot on retrospective footage with trained operators; collect misses and false alerts.
7. Complete security, privacy, reliability, procurement, and operational readiness work.

The first engineering slice should implement steps 2 and 3 without replacing the current
working detector. This creates a measurable side-by-side benchmark and a rollback path.
