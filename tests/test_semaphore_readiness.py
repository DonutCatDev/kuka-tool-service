from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from urllib.request import Request


SCRIPT = Path(__file__).parents[1] / "scripts" / "inspect_semaphore_preflight.py"
SPEC = importlib.util.spec_from_file_location("inspect_semaphore_preflight", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Response:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


def test_readiness_inspection_is_get_only_and_accepts_guarded_template() -> None:
    requests: list[Request] = []
    responses = {
        "/api/project/1/repositories": [
            {"id": 9, "git_url": MODULE.EXPECTED_REPOSITORY}
        ],
        "/api/project/1/inventory": [{"id": 4, "name": "Fleetlord"}],
        "/api/project/1/templates": [
            {
                "id": 300,
                "name": "KUKA Tool Service - read-only preflight",
                "repository_id": 9,
                "inventory_id": 4,
                "playbook": "ansible/preflight.yml",
                "app": "ansible",
                "allow_override_args_in_task": False,
            }
        ],
    }

    def opener(request: Request, timeout: int) -> Response:
        assert timeout == 10
        assert request.get_method() == "GET"
        assert request.data is None
        requests.append(request)
        path = request.full_url.removeprefix(MODULE.SEMAPHORE_URL)
        return Response(responses[path])

    result = MODULE.inspect_readiness("secret", opener=opener)

    assert result["ready"] is True
    assert result["task_launched"] is False
    assert len(requests) == 3
    assert all(request.headers["Authorization"] == "Bearer secret" for request in requests)


def test_readiness_fails_closed_without_exact_repository_and_template() -> None:
    responses = iter(
        [
            [{"id": 2, "git_url": "https://example.invalid/other.git"}],
            [{"id": 4, "name": "Fleetlord"}],
            [
                {
                    "id": 6,
                    "repository_id": 2,
                    "inventory_id": 4,
                    "playbook": "playbooks/deploy-fleet-services.yml",
                    "app": "ansible",
                    "allow_override_args_in_task": False,
                }
            ],
        ]
    )

    def opener(request: Request, timeout: int) -> Response:
        return Response(next(responses))

    result = MODULE.inspect_readiness("secret", opener=opener)

    assert result["repository_registered"] is False
    assert result["preflight_templates"] == []
    assert result["ready"] is False
    assert result["task_launched"] is False


def test_readiness_rejects_task_argument_overrides() -> None:
    responses = iter(
        [
            [{"id": 9, "git_url": MODULE.EXPECTED_REPOSITORY}],
            [{"id": 4}],
            [
                {
                    "id": 300,
                    "repository_id": 9,
                    "inventory_id": 4,
                    "playbook": "./ansible/preflight.yml",
                    "app": "ansible",
                    "allow_override_args_in_task": True,
                }
            ],
        ]
    )

    result = MODULE.inspect_readiness(
        "secret", opener=lambda request, timeout: Response(next(responses))
    )

    assert result["preflight_templates"][0]["arguments_override_disabled"] is False
    assert result["ready"] is False


def test_one_guarded_candidate_is_ready_when_an_obsolete_candidate_remains() -> None:
    responses = iter(
        [
            [{"id": 9, "git_url": MODULE.EXPECTED_REPOSITORY}],
            [{"id": 4}],
            [
                {
                    "id": 299,
                    "repository_id": 9,
                    "inventory_id": 4,
                    "playbook": "ansible/preflight.yml",
                    "app": "ansible",
                    "allow_override_args_in_task": True,
                },
                {
                    "id": 300,
                    "repository_id": 9,
                    "inventory_id": 4,
                    "playbook": "ansible/preflight.yml",
                    "app": "ansible",
                    "allow_override_args_in_task": False,
                },
            ],
        ]
    )

    result = MODULE.inspect_readiness(
        "secret", opener=lambda request, timeout: Response(next(responses))
    )

    assert result["ready"] is True
