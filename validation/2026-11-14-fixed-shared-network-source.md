# Fixed shared-network proxy address

Prepared on 2026-11-14 for the Fleetlord Docker address-allocation repair.

`compose.yaml` now requests `172.30.0.6` explicitly for
`kuka-tool-service-proxy` on the external `fleet-services` network. This
preserves its current address recorded by Fleet Control inspection task 974.
The application retains its established `172.30.0.23` address.

Local checks:

- Compose YAML, both service addresses, and external network assertions passed.
- All five existing deployment contract checks passed when invoked directly.
- `docker compose -f compose.yaml config --quiet` passed.
- The required `PYTHON=/usr/bin/python3 bash scripts/check.sh` completed its
  compilation step, then stopped because `pytest` is unavailable. The complete
  application suite and Ansible syntax checks remain pending in an environment
  with the project dependencies.

This commit prepares source only. Fleetlord endpoint conversion, network
migration, and live service acceptance belong to the parent Fleet Control
workflow and have not been performed by this change.
