# SRC-to-mesh generation local validation

Date: 2026-10-27

## Scope

Validated deterministic baseline mesh generation from strict marker-classified
SRC extrusion bounds. This is local source validation only; it is not Fleetlord
deployment, process approval, or physical robot acceptance.

## Automated checks

`scripts/check.sh` completed successfully:

- 77 tests passed;
- golden CSV output, outward bound snapping, degenerate-axis expansion, resource
  limits, browser authorization, attachment headers, and audit behavior passed;
- generated CSV output was reparsed with the production mesh parser;
- Docker was unavailable, so Compose/container validation was skipped.

## Large reference exercise

Generation ran in memory against the 20,345,352-byte reference program
`RECREATED_cell10-200007-01-back_51mm-50mm_47%_test1_edited_20__cell10-200007-01-body_60mm-50mm_47%.src`.
No output was written into the reference tree.

- input SHA-256: `9ae8fe2faf8fb02e42498c43f626ec3446e05b0d79c31b698b89fe59cd863d79`
- request: X/Y spacing 50 mm, margin 25 mm, baseline 7.5 mm
- generated bounds: X -50 through 900; Y 1550 through 2350
- grid: 20 X coordinates by 17 Y coordinates; 340 cells
- output bytes: 1,523
- output SHA-256: `7a0511ae3028d3c3394c635b2208f58a060806c3e82542cebba3b19e7baaffc7`
- reparse result: 340 measured cells, all at 7.5 mm

## Pending acceptance

- Validate the container and Compose configuration on a Docker-capable host.
- Deploy to Fleetlord only under a separately authorized deployment task.
- Have an operator confirm generated bounds and baseline values before use.
- Complete downstream compensation and physical acceptance under the applicable
  safety process.
