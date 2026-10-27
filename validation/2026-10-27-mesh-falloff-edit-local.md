# Grouped mesh falloff editing local validation

Date: 2026-10-27

## Scope

Validated radial grouped mesh editing with linear, quadratic, and cubic falloff
for set, add, subtract, and multiply operations. This is local source validation
only; it is not Fleetlord deployment, process approval, or physical robot
acceptance.

## Automated checks

`scripts/check.sh` completed successfully:

- 95 tests passed;
- golden output, all falloff curves, weighted operation semantics, missing and
  empty regions, browser authorization, attachment headers, and audit behavior
  passed;
- Docker was unavailable, so Compose/container validation was skipped.

## Reference mesh exercise

The edit ran in memory against `Cell10-200007-01_edited2.csv`. No output was
written into the reference tree.

- input bytes: 2,336
- input SHA-256: `b5c447698a0e6e7f87acc5cbeb15090eb6454f057487379dde25fffdc56a8fea`
- operation: add 0.25 mm
- center: X 415, Y 1947.74
- radius: 150 mm
- falloff: quadratic
- changed cells: 25
- independently compared numeric differences: 25
- output SHA-256: `56c9c2b4919bc5abad1560013c01b582072aef3ae143a72e21b78153422d71c8`
- axis coordinates and all 285 measured cells preserved after reparsing

## Pending acceptance

- Validate the container and Compose configuration on a Docker-capable host.
- Deploy to Fleetlord only under a separately authorized deployment task.
- Have an operator review falloff shape and generated values before downstream use.
- Complete downstream compensation and physical acceptance under the applicable
  safety process.
