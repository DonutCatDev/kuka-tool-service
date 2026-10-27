# Browser layer inspection local validation

Date: 2026-10-27

## Scope

Validated read-only strict extrusion-layer summaries and bounded SVG path
preview. This is a parsing aid only; it is not Fleetlord deployment, robot-path
simulation, engineering approval, or physical robot acceptance.

## Automated checks

`scripts/check.sh` completed successfully:

- 82 tests passed;
- layer indexing, summaries, requested-layer bounds, incomplete/empty regions,
  unterminated markers, 5,000-point preview bounding, authentication, rendering,
  and audit behavior passed;
- Docker was unavailable, so Compose/container validation was skipped.

## Large reference exercise

Inspection ran in memory against the 20,345,352-byte reference program
`RECREATED_cell10-200007-01-back_51mm-50mm_47%_test1_edited_20__cell10-200007-01-body_60mm-50mm_47%.src`.
No source or preview artifact was persisted.

- input SHA-256: `9ae8fe2faf8fb02e42498c43f626ec3446e05b0d79c31b698b89fe59cd863d79`
- strict extrusion layers: 205
- preview index: 10
- source lines: 19,933 through 20,838
- complete extrusion LIN commands: 903
- parsed/rendered preview points: 903 / 903
- Z range: 27.0 through 27.0 mm
- X range: -13.3 through 843.3 mm
- Y range: 1589.13 through 2293.76 mm
- geometric within-layer distance: 8,410.398469 mm

## Pending acceptance

- Validate the container and Compose configuration on a Docker-capable host.
- Deploy to Fleetlord only under a separately authorized deployment task.
- Have operators confirm layer indices against representative production files.
- Keep robot-path and physical-safety review separate from this XY parsing aid.
