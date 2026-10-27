# Browser path/mesh overlay local validation

Date: 2026-10-27

## Scope

Validated the read-only shared-coordinate overlay for one strict SRC extrusion
layer and one measured mesh CSV. This is a parsing and coverage aid only; it is
not Fleetlord deployment, compensation approval, robot simulation, collision
checking, or physical robot acceptance.

## Automated checks

`scripts/check.sh` completed successfully:

- 86 tests passed;
- shared coordinate scaling, measured/missing sample rendering, outside-mesh
  counting, rendering limits, authentication, HTML rendering, and dual-input
  audit behavior passed;
- Docker was unavailable, so Compose/container validation was skipped.

## Reference overlay exercise

The overlay ran in memory using the 20,345,352-byte Cell 10 reference SRC and
its `Cell10-200007-01_edited2.csv` measured mesh. No input or rendered artifact
was persisted.

- source SHA-256: `9ae8fe2faf8fb02e42498c43f626ec3446e05b0d79c31b698b89fe59cd863d79`
- mesh SHA-256: `b5c447698a0e6e7f87acc5cbeb15090eb6454f057487379dde25fffdc56a8fea`
- selected layer: 10
- mesh samples: 285 measured, 0 missing
- path points: 903 parsed, 903 rendered
- path points outside mesh coordinate bounds: 40
- combined bounds: X -35 through 865; Y 1589.13 through 2297.74
- generated polyline data: 12,367 characters

The outside count reflects points below the measured mesh's minimum Y value and
is informational; this validation does not decide whether fallback behavior or
the process geometry is acceptable.

## Pending acceptance

- Validate the container and Compose configuration on a Docker-capable host.
- Deploy to Fleetlord only under a separately authorized deployment task.
- Have operators compare overlays with representative production expectations.
- Keep compensation approval and physical-safety review separate from this view.
