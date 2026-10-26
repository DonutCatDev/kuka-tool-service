# KUKA Tool Service

KUKA Tool Service is a planned Fleetlord-hosted web application for inspecting
and transforming LFAM KUKA `.src` motion programs. It will extract the reusable
processing behavior from the earlier `large_mesh_project` desktop suite and
present it through authenticated, auditable browser workflows.

The service is intentionally an offline artifact generator. It will not connect
to KUKA controllers, deploy programs, start production, or modify robot state.

## Initial scope

The first release is planned to provide:

1. SRC inspection and idealized path-time estimation.
2. Metadata annotation and controlled output naming.
3. Velocity analysis without automatic modification.

Path merging, XYZ adjustment, probing-path generation, mesh-based speed
compensation, and browser-based mesh editing are later phases gated by golden
regression coverage and operator review.

See [`progression/implementation-plan.md`](progression/implementation-plan.md)
for the delivery plan and
[`progression/reference-project-assessment.md`](progression/reference-project-assessment.md)
for the source assessment.

## Repository status

This initial commit contains planning and repository policy only. Runtime code,
container definitions, deployment automation, and production configuration have
not yet been implemented or deployed.

## Reference source

When cloned in the engineering workspace, the prior desktop project is expected
at:

```text
../../refs/large_mesh_project/
```

That project is a read-only reference for extraction. Its virtual environments,
GUI launchers, generated project outputs, caches, and vendored dependencies must
not be copied into this repository.
