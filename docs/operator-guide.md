# KUKA Tool Service operator guide

## Safety boundary

KUKA Tool Service is an offline inspection and artifact-generation service. It
has no robot-controller credentials and does not upload, activate, or execute a
program. A successful browser operation means only that the documented parser
and structural checks passed. It does not establish collision safety, process
suitability, controller compatibility, or physical safety.

Generated SRC programs and edited meshes require independent review under the
site's normal engineering and robot acceptance process before use.

## Access roles

- `viewer` may inspect SRC and mesh files and use layer/path previews.
- `operator` and `admin` may also generate downloadable transformed artifacts.
- Every form submission requires a signed-in session and CSRF token.
- Transformations require an explicit review acknowledgement.

## Recommended workflow

1. Inspect the SRC file and review parser warnings, markers, bounds, velocities,
   and layer counts.
2. Use layer inspection to confirm the zero-based layer index when a
   layer-selective operation is planned.
3. Inspect any mesh independently. Use the path/mesh overlay to identify path
   points outside measured coverage.
4. Run one narrowly scoped transformation at a time.
5. Save the downloaded artifact with its input/output hashes and review the
   reported change count.
6. Reinspect generated SRC or mesh output where applicable.
7. Compare the output with the original using the approved engineering review
   process before any controller-side activity.

Avoid chaining several transformations without preserving and reviewing each
intermediate artifact. The service does not keep a server-side copy that can be
used as rollback storage.

## Data handling and retention

- Uploaded SRC and mesh bytes are processed in request memory and are not
  persisted by the application.
- Generated files are streamed as attachments and are not retained by the
  application.
- Source content is not stored in the audit database. Audit rows contain the
  operator identity, operation, parameters, result, and SHA-256 hashes.
- Audit rows older than `KUKA_TOOL_AUDIT_RETENTION_DAYS` are removed when a new
  audit event is written. The default is 365 days.
- After age pruning, only the newest `KUKA_TOOL_AUDIT_MAX_ROWS` rows are kept.
  The default is 100,000 rows.
- The SQLite database remains operational data under
  `/srv/sv08/appdata/kuka-tool-service/data`; Fleetlord backup and access policy
  must cover that directory if audit recovery is required.

## Output-specific cautions

- Runtime estimates exclude acceleration, blending, PTP duration, controller
  overhead, and process delays.
- XYZ changes preserve setup, travel, and wipe motions, which can change their
  relationship to the extrusion path.
- Merged paths retain primary setup/shutdown scaffolding and still require a
  complete compatibility review.
- Probe grids intentionally omit production controller setup and safety logic.
- Mesh editing can change downstream speed compensation across many motions.
- Path/mesh previews are two-dimensional and do not model Z geometry,
  orientation, robot reach, fixtures, or collisions.

## Fleetlord deployment acceptance checklist

Deployment is a separate authorized task. Before enabling operator access:

1. Validate `docker compose config` and build both images on a Docker-capable
   host.
2. Confirm the external `fleet-services` network and assigned address do not
   conflict with another service.
3. Confirm `/srv/sv08/secrets/production-desk/users.json` is root-controlled and
   matches the documented authentication schema.
4. Confirm the data and Caddy directories under
   `/srv/sv08/appdata/kuka-tool-service/` have the intended ownership, backup,
   and recovery policy.
5. Verify the HTTPS endpoint, service-specific cookie, CSRF enforcement,
   security headers, authentication roles, health checks, and audit writes.
6. Exercise representative read-only and transformation workflows without any
   robot-controller connectivity.
7. Complete operator review and separately controlled robot-side acceptance.

Prefer the established Semaphore workflow for privileged Fleetlord deployment
when its reviewed template and encrypted credentials are available. Direct SSH
with interactive `sudo` is only the documented fallback.

The repository-owned preflight, deployment, and Semaphore variable guidance is
in [`../ansible/README.md`](../ansible/README.md). Run preflight first. Deployment
requires an explicit approval variable and the exact reviewed commit revision.

## Current pilot state

The service is prepared for deployment at `https://fleetlord.local:6000`. Automated and
independent checks passed for service health, configured authentication, absence
of controller access, direct-HTTP rejection, HTTPS login, the login CSRF field,
and proxy security headers. Before general operator use, complete authenticated
role, transformation/download, and audit-write checks with approved test files.
Robot-side acceptance remains separate and incomplete.
