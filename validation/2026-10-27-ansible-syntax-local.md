# Ansible syntax validation

Date: 2026-10-27

## Scope

Validated the repository-owned Fleetlord preflight and deployment playbooks with
Ansible Core 2.19.14 against the real Fleet Control inventory. Syntax checking
does not connect to inventory hosts and no preflight or deployment was executed.

## Environment

- Python: workspace virtual environment
- Ansible Core: 2.19.14
- inventory: `../inventory/hosts.yml`
- local temporary path: writable task-specific directory
- remote temporary path declaration: `/tmp/kuka-tool-ansible-remote`

## Results

Both commands completed successfully:

```text
ansible-playbook --syntax-check -i ../inventory/hosts.yml ansible/preflight.yml
ansible-playbook --syntax-check -i ../inventory/hosts.yml ansible/deploy.yml
```

The normal repository check now runs these commands automatically when Ansible
is installed. `ansible-core==2.19.14` is available through the `deployment`
optional dependency so the validation environment is reproducible without
adding Ansible to the runtime container.

## Pending acceptance

- Docker/Compose configuration and image builds remain unvalidated locally.
- Run the read-only preflight through the established Semaphore template and
  encrypted Fleetlord credentials.
- Review and separately authorize the exact release revision before deployment.
- No Fleetlord or robot-side acceptance has been performed.
