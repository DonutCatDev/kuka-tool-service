# KUKA Tool Service implementation plan

Status: implementation in progress

Last reviewed: 2026-10-27

Current local validation evidence:
[`../validation/2026-10-26-browser-slice-local.md`](../validation/2026-10-26-browser-slice-local.md)
and
[`../validation/2026-10-27-velocity-modification-local.md`](../validation/2026-10-27-velocity-modification-local.md)
and
[`../validation/2026-10-27-xyz-adjustment-local.md`](../validation/2026-10-27-xyz-adjustment-local.md)
and
[`../validation/2026-10-27-path-merge-local.md`](../validation/2026-10-27-path-merge-local.md)
and
[`../validation/2026-10-27-probe-grid-local.md`](../validation/2026-10-27-probe-grid-local.md)
and
[`../validation/2026-10-27-mesh-parser-local.md`](../validation/2026-10-27-mesh-parser-local.md)
and
[`../validation/2026-10-27-mesh-speed-local.md`](../validation/2026-10-27-mesh-speed-local.md)

## Goal

Provide authenticated Fleetlord browser workflows for analyzing and producing
reviewable KUKA/LFAM `.src` artifacts without granting the service access to a
robot controller or production file destination.

## Fixed boundaries

- The service accepts operator-selected files and returns downloadable artifacts.
- It does not upload to a controller, activate programs, or start robot motion.
- Every input and output is identified by SHA-256.
- Generated programs require independent operator review.
- Runtime estimates are geometric estimates, not authoritative production cycle
  times.
- Deployment is a separate, explicitly authorized Fleetlord stage.

## Target architecture

Use a standalone Fleetlord service rather than embedding the tools in an
existing Production Desk application.

Target components:

- a small authenticated web application;
- a headless Python processing package with no GUI imports;
- isolated, server-generated job directories;
- SQLite metadata and audit records;
- a bounded background worker for later long-running transformations;
- expiring persisted artifacts if later workflows require server-side storage;
- container health checks and a dedicated service cookie;
- read-only Homepage and documentation links after deployment is approved.

The web process must not perform arbitrary filesystem operations from submitted
paths. Upload names are display metadata only; server-generated job and artifact
identifiers own storage paths.

## Phase 0: extraction contract and fixtures

1. Select representative `.src` fixtures covering:
   - UTF-8 and expected legacy encodings;
   - CRLF and LF line endings;
   - normal layers and travel transitions;
   - wipe moves;
   - missing or ambiguous markers;
   - large production-scale inputs.
2. Record source hashes and expected parser summaries.
3. Define the supported KRL subset and explicit rejection conditions.
4. Define deterministic output, encoding, newline, and terminal-newline rules.
5. Establish golden byte or semantic comparisons for each transformation.

Acceptance gate:

- fixtures are reviewed and contain no uncontrolled production secrets;
- parser limitations are documented;
- the Linux test environment is reproducible;
- malformed and oversized input fails closed.

## Phase 1: SRC Inspector and Time Estimator

Extract pure parsing and analysis behavior for:

- source SHA-256 and basic encoding/newline metadata;
- motion and layer counts;
- XYZ bounds;
- velocity distribution;
- travel/wipe marker summary;
- idealized path-time estimate.

The runtime result must explain that it excludes acceleration, blending, PTP
duration, controller overhead, and process delays.

Acceptance gate:

- inspection never changes the uploaded bytes;
- results are deterministic for the golden corpus;
- unsupported syntax produces warnings or rejection rather than silent success;
- file, line-count, numeric, and processing-time limits are enforced.

## Phase 2: Metadata Annotator

Add controlled metadata fields and update the KRL `DEF` name while preserving
all unrelated source content.

Acceptance gate:

- field and identifier validation is explicit;
- output naming is deterministic and sanitized;
- the UI shows the input/output hashes and a concise change summary;
- encoding and newline behavior matches the Phase 0 contract;
- output is download-only and never propagated automatically.

## Phase 3: Authenticated Fleetlord pilot

Add the browser workflow, audit database, retention cleanup, container packaging,
health endpoint, operator documentation, and local validation.

Security requirements:

- authenticated access for viewing and mutation;
- CSRF protection;
- unique session cookie name;
- secure cookie settings on the approved HTTPS boundary;
- UUID-scoped storage and attachment-only downloads;
- no secrets or source contents in application logs;
- explicit retention and cleanup policy.

Acceptance gate:

- unit, contract, golden, and route tests pass;
- container and Compose validation pass locally;
- source repository checks pass;
- deployment remains pending until separately authorized.

## Phase 4: Advanced transformations

Evaluate each operation independently:

1. Velocity modification.
2. Path merging.
3. XYZ adjustment.
4. Probing-path generation.
5. Mesh-based speed compensation.
6. Browser mesh and layer editing.

Each operation requires a separate parameter contract, validation report,
golden corpus, operator confirmation flow, and rollout decision. Path generation
or transformation must not inherit controller write authority.

Velocity modification is now implemented as the first advanced transformation.
It uses strict alternating marker classification, preserves setup velocities,
and fails closed on ambiguous marker sequences. Deployment and operator review
remain separate acceptance stages.

XYZ adjustment is implemented for all complete Cartesian LIN commands in
marker-classified extrusion regions, with optional inclusive zero-based layer
selection. Setup, return-travel, and wipe motions are preserved. Graphical
preview remains future browser-interface work. Local evidence is recorded in
[the layer-selection validation report](../validation/2026-10-27-layer-selective-xyz-local.md).

Alternating path merge is implemented for equal-count, Z-aligned programs with
compatible setup and shutdown scaffolding. It preserves original block content
and uses the primary program's header and tail. Velocity normalization remains
available as a separate transformation rather than an implicit merge side
effect.

Probe-grid generation is implemented as a deterministic review-only artifact.
It uses extrusion bounds and source orientation fields but deliberately omits
uploaded process-control scaffolding. Controller integration and physical path
validation remain separate engineering work.

Strict mesh CSV inspection and dependency-free bilinear lookup are implemented
as the parsing foundation for mesh-based speed compensation. Missing cells are
reported rather than silently replaced.

Endpoint mesh-speed compensation is implemented with golden coverage and output
reinspection. It preserves geometry and does not split moves at zone boundaries.
Historical boundary-splitting behavior remains a separately gated enhancement.

Browser mesh editing now supports one audited rectangular set/add/subtract/
multiply operation using inclusive mesh-coordinate bounds. Interactive grid
painting, previews, and undo/redo remain future browser-interface work. Local
evidence is recorded in
[the mesh-edit validation report](../validation/2026-10-27-mesh-rectangle-edit-local.md).

Grouped mesh editing now adds radial linear, quadratic, and cubic falloff for
set/add/subtract/multiply operations. Browser-side click selection and undo/redo
remain future interface work. Local evidence is recorded in
[the falloff-edit validation report](../validation/2026-10-27-mesh-falloff-edit-local.md).

SRC-to-mesh generation now provides the other half of the browser zone workflow:
strict extrusion bounds become a complete baseline CSV grid that can feed mesh
editing and compensation. Interactive path overlays remain future interface work.
Local evidence is recorded in
[the mesh-generation validation report](../validation/2026-10-27-src-mesh-generation-local.md).

Read-only browser layer inspection now lists the same strict zero-based
extrusion regions used by transformations and renders one bounded XY path
preview. Mesh/path overlay and interactive point selection remain future work.
Local evidence is recorded in
[the layer-inspection validation report](../validation/2026-10-27-layer-inspection-local.md).

Read-only mesh/path overlay is now implemented with shared XY scaling, measured
height colors, explicit missing samples, full parsed coverage accounting, and
bounded SVG/HTML rendering. Interactive point selection remains future work.
Local evidence is recorded in
[the overlay validation report](../validation/2026-10-27-path-mesh-overlay-local.md).

## Initial repository work

- [x] Create the independent nested repository.
- [x] Add repository and service-specific operating guidance.
- [x] Add planning and reference-assessment records.
- [x] Add ignore rules for secrets, runtime state, uploads, artifacts, and caches.
- [ ] Select and sanitize the golden fixture corpus.
- [x] Add a synthetic golden fixture for velocity replacement.
- [x] Add a synthetic golden fixture for XYZ adjustment.
- [x] Add synthetic golden fixtures for alternating path merge.
- [x] Add synthetic golden fixtures for probe-grid generation.
- [x] Add strict mesh CSV parsing and inspection fixtures.
- [x] Define the initial package and route contracts.
- [x] Implement Phase 1 inspection and time estimation.
- [x] Implement the first metadata-annotation browser workflow.
- [x] Add initial container and Compose definitions.
- [x] Implement marker-aware velocity modification.
- [x] Implement marker-aware extrusion XYZ adjustment.
- [x] Implement strict alternating path merge.
- [x] Implement bounded review-only probe-grid generation.
- [x] Implement the mesh parsing/interpolation foundation.
- [x] Implement endpoint mesh-speed compensation.
- [ ] Add Fleet Control deployment automation after local acceptance.
- [ ] Perform a separately authorized Fleetlord pilot deployment.
