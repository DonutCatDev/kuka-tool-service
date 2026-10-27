# Velocity modification local validation

Date: 2026-10-27

Scope: source, unit, golden-fixture, and read-only reference validation for the
marker-aware velocity transformation. This is not Fleetlord deployment,
operator approval, KRL controller validation, or robot-side acceptance.

## Contract exercised

- Preserve `$VEL.CP` assignments before the first travel marker.
- Classify extrusion after `;travel end` and return travel after
  `;travel start`.
- Require marker types to alternate and reject ambiguous sequences.
- Replace signed, leading-decimal, decimal, and scientific-notation values.
- Preserve encoding, dominant newline style, terminal newline, comments, and
  unrelated source text.
- Return attachment-only output with input/output hashes and an audit record.

## Automated checks

Command:

```text
PYTHON=.venv/bin/python scripts/check.sh
```

Result: 24 tests passed on Python 3.13.5. Syntax compilation completed. Docker
was unavailable, so Compose validation was skipped by the check script.

The tests include a synthetic byte-for-byte golden pair under
`tests/fixtures/velocity/`, malformed marker rejection, CP1252/CRLF fidelity,
browser authentication and authorization, CSRF enforcement, attachment
headers, SHA-256 provenance, and SQLite audit assertions.

## Read-only production-scale reference

Input SHA-256:
`9ae8fe2faf8fb02e42498c43f626ec3446e05b0d79c31b698b89fe59cd863d79`

The 20,345,352-byte reference was read from the workspace reference project and
transformed entirely in memory using extrusion velocity `0.047 m/s` and travel
velocity `0.125 m/s`. No generated output was written back to the reference
tree.

- output SHA-256:
  `6e471287e152bcdace65df428192067239e043c9d579127b2a1c4b12b7d3abe0`
- changed velocity lines: 6,172
- parsed LIN commands after transformation: 151,176
- parsed PTP commands after transformation: 1
- extrusion blocks after transformation: 205
- grouped Z layers after transformation: 203
- wipes after transformation: 203
- parser warnings after transformation: 0

## Remaining acceptance

- Build and run the container and validate the Compose project on a Docker host.
- Review representative generated diffs with a KUKA/LFAM operator.
- Validate requested speed limits and generated KRL independently before any
  controller-side or physical robot use.
- Perform Fleetlord deployment only under a separate explicit authorization.
