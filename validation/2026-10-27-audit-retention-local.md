# Audit retention and operator guidance local validation

Date: 2026-10-27

## Scope

Validated bounded SQLite audit retention and documented the operator workflow,
data lifecycle, and Fleetlord deployment acceptance checklist. This is local
validation only; no Fleetlord deployment or external system change was made.

## Retention contract

- Uploaded SRC and mesh bytes remain request-memory only.
- Generated downloads are streamed and not persisted by the application.
- Audit rows are pruned in the same transaction as each new audit event.
- Rows older than `KUKA_TOOL_AUDIT_RETENTION_DAYS` are removed first.
- The remaining table is capped to the newest `KUKA_TOOL_AUDIT_MAX_ROWS` rows.
- Defaults are 365 days and 100,000 rows.
- Invalid bounds degrade the health endpoint instead of silently disabling
  retention.

## Automated checks

`scripts/check.sh` completed successfully:

- 97 tests passed;
- a seeded expired row was removed;
- a seeded table exceeding the configured cap retained only the newest rows,
  including the newly written audit event;
- invalid retention configuration produced degraded health with a diagnostic;
- Docker was unavailable, so Compose/container validation was skipped.

## Documentation review

`docs/operator-guide.md` now records roles, recommended review sequence,
memory-only upload/download behavior, audit contents and retention, output risks,
and the pre-deployment Fleetlord acceptance checklist. `README.md` now reflects
the implemented service rather than the initial three-feature slice.

## Pending acceptance

- Validate Compose configuration and container builds on a Docker-capable host.
- Confirm production retention values with the audit/operations owner.
- Confirm backup and recovery policy for the Fleetlord SQLite data directory.
- Deploy only under a separately authorized task, preferably through Semaphore.
