# XYZ adjustment local validation

Date: 2026-10-27

Scope: source, unit, golden-fixture, and read-only reference validation for the
marker-aware XYZ transformation. This does not establish Fleetlord deployment,
operator approval, KRL controller validity, collision safety, or robot-side
acceptance.

## Contract exercised

- Adjust complete Cartesian LIN commands only inside extrusion regions.
- Preserve setup, PTP, return-travel, and wipe motions.
- Recognize coordinate fields in arbitrary order and numeric values using
  signs, leading decimals, or scientific notation.
- Reject incomplete and duplicate XYZ fields or ambiguous travel markers.
- Bound each finite offset to -1000 through 1000 mm and reject a no-op request.
- Preserve encoding, dominant newline style, terminal newline, comments, and
  unrelated source text.
- Require authentication, operator role, CSRF, and explicit review
  acknowledgement; return attachment-only output with hashes and audit data.

## Automated checks

Command:

```text
PYTHON=.venv/bin/python scripts/check.sh
```

Result: 29 tests passed on Python 3.13.5. Syntax compilation completed. Docker
was unavailable, so Compose validation could not run locally.

The suite includes a synthetic byte-for-byte golden pair under
`tests/fixtures/xyz/`, field-order and numeric-format coverage, CP1252/CRLF
fidelity, incomplete-motion rejection, parameter limits, travel preservation,
authorization, attachment headers, SHA-256 provenance, and audit assertions.

## Read-only production-scale reference

Input SHA-256:
`9ae8fe2faf8fb02e42498c43f626ec3446e05b0d79c31b698b89fe59cd863d79`

The 20,345,352-byte reference was read from the workspace reference project and
transformed entirely in memory with offsets X `+1.25 mm`, Y `-2.0 mm`, and Z
`+0.5 mm`. No output was written to the reference tree.

- output SHA-256:
  `11d5e26e8254ae3729e03ae0583ae17ef690c12f6dbc122f62627fb15e3ae4d0`
- changed extrusion LIN lines: 150,968
- LIN commands before/after: 151,176 / 151,176
- extrusion blocks before/after: 205 / 205
- parser warnings after transformation: 0

The inspector's wipe count changes from 203 to 0 because extrusion Z values are
offset while deliberately preserved wipe/travel coordinates are not. This is
expected under the defined extrusion-only contract and is a material reason for
the mandatory independent operator review.

## Remaining acceptance

- Build and run the container and validate Compose on a Docker host.
- Review representative before/after coordinates and preserved entry, return,
  and wipe paths with a KUKA/LFAM operator.
- Independently validate workspace limits, reachability, collision clearance,
  and generated KRL before controller or physical robot use.
- Perform Fleetlord deployment only under separate explicit authorization.
