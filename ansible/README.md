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

The current general Fleetlord dashboard template (project 1/template 6) is not
suitable: it checks out the parent Fleet Control repository and runs a different
playbook. Register this nested repository as its own Semaphore repository before
creating either template. For the preflight template, select:

- repository `https://github.com/DonutCatDev/kuka-tool-service.git`;
- the established Fleetlord-only inventory and encrypted SSH/root-become keys;
- application `Ansible` and playbook `ansible/preflight.yml`;
- no task-time argument overrides.

After registration, inspect those links without launching a task:

```bash
python3 scripts/inspect_semaphore_preflight.py \
  --token-file ~/.config/work_sv08/semaphore-dashboard.token
```

The inspector makes only three authenticated GET requests. Exit status `0`
means it found a matching Ansible template with an existing inventory and
argument overrides disabled; status `2` means registration is incomplete. It
does not validate encrypted key selection, inventory contents, or branch/release
pinning, which must still be reviewed in the Semaphore UI.

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
