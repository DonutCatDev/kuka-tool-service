# Fleetlord deployment automation

These playbooks are intended for Fleet Control's established Semaphore execution
plane. They do not grant controller access and must not be aimed at printer
inventory groups.

## Recommended templates

Create two templates against this repository and the established Fleet Control
inventory and encrypted Fleetlord SSH/root-become credentials:

1. `ansible/preflight.yml` — read-only prerequisite inspection. Disable
   task-time argument overrides.
2. `ansible/deploy.yml` — explicit pilot deployment. Disable task-time argument
   overrides and provide fixed reviewed variables based on
   `semaphore-vars.example.yml`.

The deployment template must set `kuka_tool_deployment_approved: true` and the
exact lowercase Git commit selected for deployment. The playbook records that
revision at `/opt/stacks/kuka-tool-service/RELEASE`. Leaving approval false or
omitting a valid revision fails before any write.

## Preflight guarantees

The read-only preflight:

- restricts itself to the `fleetlord` inventory host at `fleetlord.local`;
- requires the established root-owned mode-0600 Production Desk users secret;
- verifies Docker, Docker Compose, and the external `fleet-services` network;
- validates the existing deployed Compose file when one is present;
- performs no deployment or controller access.

## Deployment behavior

The deployment playbook:

- repeats all host, secret, Docker, and network guards;
- creates only the service's stack and appdata directories;
- copies the reviewed runtime allowlist from the checked-out revision;
- validates Compose before starting containers;
- rebuilds only when source or the recorded revision changes;
- checks application health, verifies direct HTTP fails closed, and checks the
  HTTPS login boundary;
- reports robot acceptance as incomplete.

The Caddy check disables certificate-chain validation because the service uses
Caddy's internal CA. Separately verify the expected certificate and client trust
during pilot acceptance.

Running either playbook is a deployment action and remains outside source-only
development tasks. Prefer Semaphore; direct SSH plus interactive `sudo` is only
the documented fallback when Semaphore cannot perform the scoped operation.

For local syntax validation without contacting Fleetlord, install the pinned
`deployment` optional dependency and run `scripts/check.sh`. The check uses the
Fleet Control inventory only for parsing and does not execute either playbook.
