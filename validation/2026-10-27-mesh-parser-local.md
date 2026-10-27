# Mesh CSV parser local validation

Date: 2026-10-27

Scope: strict CSV parsing, browser inspection, interpolation, and reference
speed-zone calculation. Mesh-compensated SRC generation, Fleetlord deployment,
operator approval, and robot acceptance are not included.

## Contract exercised

- Parse the historical X-row/Y-column mesh matrix with standard CSV quoting.
- Require rectangular rows, a blank top-left field, finite values, and strictly
  increasing unique axes.
- Report measured and missing cells without silently filling gaps.
- Bound uploads to 8 MiB, 2,000 values per axis, and 1,000,000 cells.
- Perform dependency-free bilinear interpolation only when all four corners are
  measured; use an explicit baseline for gaps and out-of-bounds lookups.
- Recreate the reference height-zone speed calculation with bounded parameters.
- Require browser authentication and CSRF and record inspection hashes.

## Automated checks

Command:

```text
PYTHON=.venv/bin/python scripts/check.sh
```

Result: 53 tests passed on Python 3.13.5. Syntax compilation completed. Docker
was unavailable, so Compose validation could not run locally.

Coverage includes grid summaries, missing values, bilinear interpolation,
baseline fallback, malformed and non-finite fields, duplicate axes, ragged
rows, empty measurement templates, speed zones, browser rendering, and audit
evidence.

## Read-only reference CSV checks

No reference file was changed or copied into the service repository.

- `Cell04-200001-01.csv`
  - SHA-256: `ac77eb63479b511ad8920638c575b4092a6ea5a4bc31cc06886b5dea109f585e`
  - grid: 5 X rows by 34 Y columns
  - measured/missing: 170 / 0
  - height range: 2.110000 to 3.840000 mm
- `Cell10-200007-01_edited2.csv`
  - SHA-256: `b5c447698a0e6e7f87acc5cbeb15090eb6454f057487379dde25fffdc56a8fea`
  - grid: 19 X rows by 15 Y columns
  - measured/missing: 285 / 0
  - height range: 6.420000 to 8.520000 mm
- `test_200013_probing_path.csv` was correctly rejected because all 225 height
  cells are blank; it is a probing template, not a measured mesh.

## Remaining acceptance

- Define and review the mesh-compensated SRC transformation contract.
- Build and run the container and validate Compose on a Docker host.
- Validate any later generated speed changes with a KUKA/LFAM operator and
  approved offline/physical procedures.
- Deploy to Fleetlord only under separate explicit authorization.
