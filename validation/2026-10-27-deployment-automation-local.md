# Fleetlord deployment automation local validation

Date: 2026-10-27

## Scope

Prepared repository-owned, Semaphore-oriented Fleetlord preflight and deployment
playbooks. This validation is source-only. No Semaphore task, SSH session,
Fleetlord preflight, Compose action, or deployment was performed.

## Automation boundary

- `ansible/preflight.yml` is read-only and restricted to the `fleetlord` host at
  `fleetlord.local`.
- `ansible/deploy.yml` is serialized, repeats host and secret guards, and fails
  before writes unless explicit approval and a lowercase 7-40 character Git
  revision are provided.
- The deployment checks the established root-owned mode-0600 Production Desk
  users secret and existing `fleet-services` Docker network.
- Only an allowlist of runtime files is copied.
- Compose is validated before startup.
- Post-start checks require healthy authentication, no controller access, HTTP
  fail-closed behavior, and the HTTPS login boundary.
- The reported state keeps robot acceptance false.

## Local checks

`scripts/check.sh` completed successfully:

- 101 tests passed;
- four static deployment-contract tests passed for host restrictions, read-only
  preflight behavior, approval/revision gates, secret permissions, Compose
  validation, health checks, HTTPS, and explicit incomplete robot acceptance;
- `bash -n scripts/check.sh` passed;
- Docker was unavailable, so Compose validation and image builds were skipped;
- Ansible was unavailable, so `ansible-playbook --syntax-check` was skipped.

The check script now runs both Ansible syntax checks automatically when Ansible
is installed.

## Pending acceptance

1. Run `ansible-playbook --syntax-check` for both playbooks in the Semaphore or
   another matching Ansible environment.
2. Run the read-only preflight through the established Semaphore credentials.
3. Validate Compose and build the images on Fleetlord or another Docker-capable
   host.
4. Review the exact pushed release revision and separately authorize deployment.
5. Perform HTTPS, role, audit, operator, and robot-side acceptance after the
   source deployment succeeds.
