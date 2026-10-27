# KUKA Tool Service

KUKA Tool Service is a Fleetlord-targeted web application for inspecting and
transforming LFAM KUKA `.src` motion programs. It recreates the reusable
processing behavior from the earlier `large_mesh_project` desktop suite as
authenticated, auditable browser workflows.

The service is intentionally an offline artifact generator. It will not connect
to KUKA controllers, deploy programs, start production, or modify robot state.

## Delivery scope

The first browser slice provides:

1. SRC inspection and idealized path-time estimation.
2. Metadata annotation and controlled output naming.
3. Marker-aware velocity analysis and controlled modification.

Path merging, XYZ adjustment, probing-path generation, mesh-based speed
compensation, and browser-based mesh editing are later phases gated by golden
regression coverage and operator review.

See [`progression/implementation-plan.md`](progression/implementation-plan.md)
for the delivery plan and
[`progression/reference-project-assessment.md`](progression/reference-project-assessment.md)
for the source assessment.

## Current implementation

The first browser-service slice provides:

- authenticated `.src` inspection;
- motion, velocity, marker, layer, wipe, bounds, and hash reporting;
- idealized LIN-path runtime estimation;
- operator-only metadata annotation and renamed artifact download;
- operator-only extrusion and return-travel velocity replacement;
- operator-only XYZ offsets for marker-classified extrusion LIN motions;
- operator-only alternating merge of structurally compatible path programs;
- source/output SHA-256 provenance and SQLite audit records;
- encoding and newline preservation for generated artifacts;
- a container and local Compose definition.

The service has no controller access or automatic program propagation. See
[`docs/service-contract.md`](docs/service-contract.md) for the exact supported
parsing and authorization contract.

## Local development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
PYTHON=.venv/bin/python scripts/check.sh
```

The application requires a users JSON file using the existing Production Desk
secret schema. Point `KUKA_TOOL_USERS_PATH` at a local non-committed fixture and
set `KUKA_TOOL_REQUIRE_HTTPS=false` only for local development.

## Deployment status

Source implementation and local validation are separate from deployment. The
service has not been deployed to Fleetlord and has not undergone operator or
robot-side acceptance.

## Reference source

When cloned in the engineering workspace, the prior desktop project is expected
at:

```text
../../refs/large_mesh_project/
```

That project is a read-only reference for extraction. Its virtual environments,
GUI launchers, generated project outputs, caches, and vendored dependencies must
not be copied into this repository.
