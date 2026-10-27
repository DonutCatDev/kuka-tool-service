# Mesh rectangle editing local validation

Date: 2026-10-27

## Scope

Validated the authenticated rectangular mesh-edit workflow for inclusive
coordinate bounds and set/add/subtract/multiply operations. This is local source
validation only; it is not Fleetlord deployment, process approval, or physical
robot acceptance.

## Automated checks

`scripts/check.sh` completed successfully:

- 69 tests passed;
- golden CSV output, malformed selection, result bounds, BOM/CRLF retention,
  browser authorization, attachment headers, and audit behavior passed;
- Docker was unavailable, so Compose/container validation was skipped.

## Reference mesh exercise

The edit ran in memory against the measured reference mesh
`Cell10-200007-01_edited2.csv`. No output was written into the reference tree.

- input bytes: 2,336
- input SHA-256: `b5c447698a0e6e7f87acc5cbeb15090eb6454f057487379dde25fffdc56a8fea`
- grid: 19 X coordinates by 15 Y coordinates; 285 measured cells
- edit: add 0.125 mm where X is 15 through 115 and Y is 1647.74 through 1747.74
- changed cells: 9
- independently compared numeric differences: 9
- output SHA-256: `c3ae57f1bc288e98f95f89fa62ab7496935e8484780c8a4f7d2056af08cb8e7c`
- axis coordinates and measured-cell count preserved after reparsing

An initial local exercise revealed that six-decimal canonicalization could alter
untargeted high-precision values. The serializer was corrected before commit;
the repeated exercise showed that only the nine selected values differed.

## Pending acceptance

- Validate the container and Compose configuration on a Docker-capable host.
- Deploy to Fleetlord only under a separately authorized deployment task.
- Have an operator review generated meshes and their downstream compensation.
- Complete robot-side and physical acceptance under the applicable safety process.
