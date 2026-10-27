from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[1]
PREFLIGHT = (ROOT / "ansible" / "preflight.yml").read_text()
DEPLOY = (ROOT / "ansible" / "deploy.yml").read_text()


def test_playbooks_are_host_guarded_serial_and_controller_free() -> None:
    for playbook in (PREFLIGHT, DEPLOY):
        assert 'inventory_hostname == "fleetlord"' in playbook
        assert 'ansible_host == "fleetlord.local"' in playbook
        assert "serial: 1" in playbook
        assert "controller_access" in playbook
        assert "kuka-status" not in playbook


def test_preflight_contains_no_mutating_deployment_tasks() -> None:
    assert "ansible.builtin.copy:" not in PREFLIGHT
    assert "ansible.builtin.file:" not in PREFLIGHT
    assert "compose, up" not in PREFLIGHT
    assert "deployment_performed: false" in PREFLIGHT


def test_deployment_requires_approval_revision_and_protected_secret() -> None:
    assert "kuka_tool_deployment_approved" in DEPLOY
    assert "kuka_tool_release_revision" in DEPLOY
    assert "^[0-9a-f]{7,40}$" in DEPLOY
    assert "/srv/sv08/secrets/production-desk/users.json" in DEPLOY
    assert 'kuka_tool_users.stat.mode == "0600"' in DEPLOY
    assert "docker, compose, config, --quiet" in DEPLOY


def test_deployment_verifies_health_https_and_http_fail_closed() -> None:
    assert "http://127.0.0.1:4700/healthz" in DEPLOY
    assert "not kuka_tool_health.json.controller_access" in DEPLOY
    assert "http://127.0.0.1:4700/login" in DEPLOY
    assert "status_code: 426" in DEPLOY
    assert "https://fleetlord.local:4743/login" in DEPLOY
    assert "robot_acceptance_complete: false" in DEPLOY
