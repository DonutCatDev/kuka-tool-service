# Probe-grid generation local validation

Date: 2026-10-27

Scope: source, unit, golden-fixture, route, and read-only reference validation
for review-only probe-grid generation. This does not establish Fleetlord
deployment, controller integration, path safety, or physical robot acceptance.

## Contract exercised

- Derive bounds only from complete marker-classified extrusion LIN commands.
- Preserve non-XYZ orientation/external-axis fields from the first extrusion
  motion without copying source process-control scaffolding.
- Generate row/column and one-way/zigzag traversal deterministically.
- Emit safe-height travel, probe descent, HALT, and safe return per grid point.
- Require safe Z above probe Z and bound spacing, margin, speeds, coordinates,
  output bytes, and grid point count.
- Preserve source encoding and newline convention in the generated artifact.
- Require authentication, operator role, CSRF, and explicit acknowledgement.
- Return attachment-only output with input/output hashes and audit parameters.

## Automated checks

Command:

```text
PYTHON=.venv/bin/python scripts/check.sh
```

Result: 44 tests passed on Python 3.13.5. Syntax compilation completed. Docker
was unavailable, so Compose validation could not run locally.

Coverage includes a byte-for-byte golden program, deterministic output,
extrusion-only bounds, field-order/orientation preservation, invalid parameter
rejection, the 10,000-point limit, browser authorization, attachment headers,
and SQLite audit evidence.

## Read-only production-scale reference

Input SHA-256:
`9ae8fe2faf8fb02e42498c43f626ec3446e05b0d79c31b698b89fe59cd863d79`

The 20,345,352-byte reference was read from the workspace reference project.
A column-priority zigzag grid was generated entirely in memory with 50 mm
spacing, safe Z 900 mm, probe Z 850 mm, travel speed 0.15 m/s, and probe speed
0.055 m/s. No artifact was written to the reference tree.

- output SHA-256:
  `5ea6004f132f019ae9a6cbdf9d891d65ceca0bcefaf8671e2708669e6df5aa9d`
- output bytes: 160,681
- grid points / HALTs: 323 / 323
- generated LIN commands: 969
- generated bounds: X -35.000 to 865.000 mm; Y 1538.485 to 2338.485 mm

## Remaining acceptance

- Build and run the container and validate Compose on a Docker host.
- Have a KUKA engineer supply and review required tool/base, safety, entry/exit,
  probe acquisition, and shutdown integration.
- Validate reachability, collision clearance, Z direction, speeds, and HALT
  behavior offline and then under an approved physical test procedure.
- Deploy to Fleetlord only under separate explicit authorization.
