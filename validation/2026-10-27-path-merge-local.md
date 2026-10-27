# Alternating path merge local validation

Date: 2026-10-27

Scope: source, unit, golden-fixture, route, and read-only reference validation
for strict alternating path merge. This does not establish Fleetlord deployment,
operator approval, controller validity, transition safety, or robot acceptance.

## Contract exercised

- Extract complete blocks using travel-end/travel-start marker order.
- Retain an immediately following same-Z wipe with its source block.
- Alternate primary then secondary blocks without rewriting block contents or
  velocities.
- Require equal block counts and paired Z heights within 0.05 mm.
- Require compatible program scaffolding and matching encoding/newline rules.
- Use only the primary header, DEF name, final return, and shutdown tail.
- Reparse the output and require the expected combined block count.
- Record both input hashes, output hash, block counts, and operator identity.
- Require authentication, operator role, CSRF, and review acknowledgement.

## Automated checks

Command:

```text
PYTHON=.venv/bin/python scripts/check.sh
```

Result: 35 tests passed on Python 3.13.5. Syntax compilation completed. Docker
was unavailable, so Compose validation could not run locally.

Coverage includes a byte-for-byte golden merge, two-input provenance, duplicate
input rejection, Z mismatch, header/tail incompatibility, unequal block counts,
output reinspection, browser authorization, attachment response, and SQLite
audit evidence.

## Read-only production-scale reference pair

The following existing primary/secondary pair was read from the reference tree
and merged entirely in memory. No output was written to the reference project.

- primary SHA-256:
  `96ce613231b56b5753f38defdbe59aa0fa10eb423644c09f9ab19796e6fefc1d`
- secondary SHA-256:
  `63c5771b856cf34d46c67a6b47644b4a3bbe3c7e3e4b313401d361d6497bbd88`
- output SHA-256:
  `5ad3e210b646d520acf246209066d7a8048a73313552c2a6af6f7e2a254553cd`
- primary/secondary blocks: 162 / 162
- output bytes: 12,451,023
- output LIN commands: 94,292
- output PTP commands: 1
- output extrusion blocks: 324
- output parser warnings: 0

## Remaining acceptance

- Build and run the container and validate Compose on a Docker host.
- Have a KUKA/LFAM operator review real inter-block transitions, first-entry
  behavior, final return, and shutdown ownership.
- Independently validate reachability, collisions, process timing, and KRL on
  the intended controller before physical robot use.
- Deploy to Fleetlord only under separate explicit authorization.
