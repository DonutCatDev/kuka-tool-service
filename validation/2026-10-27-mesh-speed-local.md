# Endpoint mesh-speed compensation local validation

Date: 2026-10-27

Scope: endpoint-derived speed insertion using a validated mesh CSV. This does
not cover historical move splitting at zone boundaries, Fleetlord deployment,
operator approval, controller validation, or physical robot acceptance.

## Contract exercised

- Parse both SRC and mesh inputs under their established resource limits.
- Modify only complete marker-classified extrusion LIN commands with an active
  positive `$VEL.CP` assignment.
- Use bilinear mesh height at each motion target endpoint.
- Use the explicit baseline for missing corners and out-of-grid coordinates and
  record the number of such fallbacks.
- Recreate the reference zone/speed formula with bounded finite parameters.
- Preserve coordinates, travel motions, encoding, newlines, and terminal
  newline state.
- Reparse output and require unchanged LIN count and complete Cartesian motions.
- Require authentication, operator role, CSRF, and explicit review
  acknowledgement.
- Return and audit source, mesh, and output hashes plus transformation counts.

## Automated checks

Command:

```text
PYTHON=.venv/bin/python scripts/check.sh
```

Result: 58 tests passed on Python 3.13.5. Syntax compilation completed. Docker
was unavailable, so Compose validation could not run locally.

Coverage includes byte-for-byte golden output, zone calculations, no-op
rejection, missing/out-of-range fallback accounting, coordinate preservation,
CP1252/CRLF fidelity, output reinspection, browser authorization, attachment
headers, dual-input provenance, and SQLite audit evidence.

## Read-only production-scale reference pair

The matching Cell10 SRC and measured mesh were read from the reference tree and
processed entirely in memory using baseline 7.3 mm, zone step 0.1 mm, speed-step
fraction 0.02, and tolerance 0.0001 m/s. No output was written to the reference
project.

- source SHA-256:
  `9ae8fe2faf8fb02e42498c43f626ec3446e05b0d79c31b698b89fe59cd863d79`
- mesh SHA-256:
  `b5c447698a0e6e7f87acc5cbeb15090eb6454f057487379dde25fffdc56a8fea`
- output SHA-256:
  `c1275e3b516406a3d341c62fa48c69d9570448169f2ebf27c0fd135e028ac71f`
- output bytes: 20,815,712
- extrusion motions evaluated: 150,968
- speed assignments inserted: 23,518
- baseline fallbacks: 2,250
- LIN count preservation: verified by output reinspection

## Remaining acceptance

- Review whether boundary splitting is required for the production process or
  endpoint compensation is the intended operating mode.
- Build and run the container and validate Compose on a Docker host.
- Have a KUKA/LFAM operator review speed transitions and fallback locations.
- Validate controller syntax, process behavior, and physical motion using an
  approved test procedure before production use.
- Deploy to Fleetlord only under separate explicit authorization.
